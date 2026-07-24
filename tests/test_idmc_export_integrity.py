"""Regression tests for IDMC sample-backed rewrite integrity and IICS validation."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from business.export.idmc_export_package import IdmcExportPackageGenerator, _AssetIds
from business.export.repair_idmc_export import repair_dtemplate_zip, repair_export_package, repair_mtt_zip
from business.iics.iics_package_processor import IICSAsset, IICSPackageProcessor


def _dtemplate_bytes(
    mapping_name: str,
    *,
    declared_size: int | None = None,
    content_name: str | None = None,
    asset_guid: str = "dtGuid123456789012345",
    include_class_info: bool = True,
) -> bytes:
    payload = {
        "content": {"$$IID": "stringIdentity:@2", "$$class": 1, "name": content_name or mapping_name},
    }
    if include_class_info:
        payload["metadata"] = {
            "$$classInfo": {
                "1": "com.informatica.metadata.template.common.Template",
                "8": "com.informatica.metadata.template.tx.tmpltarget.TmplTarget",
            }
        }
    bin_payload = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    size = len(bin_payload) if declared_size is None else declared_size
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "mappingTemplate.json",
            json.dumps(
                [
                    {
                        "@type": "mappingTemplate",
                        "id": "@1",
                        "name": mapping_name,
                        "assetFrsGuid": asset_guid,
                        "templateId": "@2",
                    }
                ],
                separators=(",", ":"),
            ),
        )
        zf.writestr(
            "fileRecord.json",
            json.dumps(
                [
                    {
                        "@type": "fileRecord",
                        "id": "@2",
                        "name": mapping_name,
                        "type": "IMFOBJECT",
                        "size": size,
                        "additionalInfo": "com.informatica.metadata.template.common.Template",
                    }
                ],
                separators=(",", ":"),
            ),
        )
        zf.writestr("bin/@2.bin", bin_payload)
        zf.writestr("metadata.meta", json.dumps([{"@type": "objectRef", "id": "@1", "type": "mappingTemplate"}]))
    return buffer.getvalue()


def _mtt_bytes(mapping_name: str, *, short_description: str, dtemplate_guid: str, mtt_guid: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "mtTask.json",
            json.dumps(
                [
                    {
                        "@type": "mtTask",
                        "id": "@1",
                        "name": mapping_name,
                        "shortDescription": short_description,
                        "mappingId": f"@{dtemplate_guid}",
                        "frsGuid": mtt_guid,
                    }
                ],
                separators=(",", ":"),
            ),
        )
        zf.writestr("metadata.meta", json.dumps([{"@type": "objectRef", "id": "@1", "type": "mtTask"}]))
    return buffer.getvalue()


class IdmcExportIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = MagicMock()
        self.config.paths.output_folder = "output"
        self.logger = MagicMock()
        self.generator = IdmcExportPackageGenerator(config=self.config, logger=self.logger)
        self.now = datetime(2026, 7, 15, tzinfo=timezone.utc)
        self.ids = _AssetIds(
            project="p",
            folder="f",
            connection="c",
            agent_group="a",
            dtemplate="tkPDqY1CGeFSKRlk75kWc7",
            mtt="ZrpIRPssN8x952awW83Aj5",
            taskflow="t",
        )

    def test_sample_rewrite_syncs_file_record_size_after_rename(self) -> None:
        sample_name = "JEG_SDE_IPCS_BItimePhasedDataBudgetFact"
        target_name = "SDE_ORA_JobDimension"
        source = _dtemplate_bytes(sample_name)

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / f"{target_name}.DTEMPLATE.zip"
            self.generator._rewrite_sample_zip(
                source,
                output,
                {sample_name: target_name, "oldDt": self.ids.dtemplate},
                self.generator._rewrite_dtemplate_member,
                target_name,
                self.ids,
                self.now,
            )
            with zipfile.ZipFile(output) as zf:
                records = json.loads(zf.read("fileRecord.json").decode("utf-8"))
                template = json.loads(zf.read("mappingTemplate.json").decode("utf-8"))[0]
                object_record = next(record for record in records if record["type"] == "IMFOBJECT")
                preview_record = next(record for record in records if record["type"] == "IMAGE")
                bin_bytes = zf.read(f"bin/{object_record['id']}.bin")
                payload = json.loads(bin_bytes.decode("utf-8"))
                preview_bytes = zf.read(f"bin/{preview_record['id']}.bin")

            self.assertEqual(len(bin_bytes), object_record["size"])
            self.assertEqual(target_name, object_record["name"])
            self.assertEqual(target_name, payload["content"]["name"])
            self.assertEqual(target_name, template["name"])
            self.assertEqual(self.ids.dtemplate, template["assetFrsGuid"])
            self.assertEqual("@2", template["mappingPreviewFileRecordId"])
            self.assertEqual("@2", preview_record["id"])
            self.assertEqual(object_record["id"], template["templateId"])
            self.assertTrue(preview_bytes.startswith(b"\x89PNG\r\n\x1a\n") or preview_bytes.startswith(b"\xff\xd8"))

    def test_sde_preview_is_rendered_from_remediated_mapping_when_reference_has_no_image(self) -> None:
        try:
            import PIL  # noqa: F401
        except Exception:
            self.skipTest("Pillow is required for mapping-aware preview rendering")

        with tempfile.TemporaryDirectory() as tmp:
            self.generator.output_folder = Path(tmp)
            self.generator.remediated_folder = Path("output/remediated_xml")
            self.generator._exact_native_package_preview_bytes = MagicMock(return_value=None)
            self.generator._reference_package_preview_bytes = MagicMock(return_value=None)
            self.generator._pinned_mapping_preview_bytes = MagicMock(return_value=None)

            preview = self.generator._mapping_reference_preview_bytes("SDE_ORA_JobDimension")

            self.assertTrue(preview.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertNotEqual(
                IdmcExportPackageGenerator._preview_bytes("SDE_ORA_JobDimension"),
                preview,
            )
            self.assertTrue((Path(tmp) / "downloadable_mapping_images_from_zip" / "SDE_ORA_JobDimension_valid_mapping.png").exists())

    def test_assert_dtemplate_integrity_rejects_missing_class_info(self) -> None:
        broken = _dtemplate_bytes("SDE_ORA_JobDimension", include_class_info=False)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "SDE_ORA_JobDimension.DTEMPLATE.zip"
            path.write_bytes(broken)
            with self.assertRaisesRegex(ValueError, r"metadata\.\$\$classInfo"):
                IdmcExportPackageGenerator._assert_dtemplate_integrity(path, "SDE_ORA_JobDimension")

    def test_assert_dtemplate_integrity_rejects_size_mismatch(self) -> None:
        broken = _dtemplate_bytes("SDE_ORA_JobDimension", declared_size=99999)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "SDE_ORA_JobDimension.DTEMPLATE.zip"
            path.write_bytes(broken)
            with self.assertRaisesRegex(ValueError, "fileRecord size mismatch"):
                IdmcExportPackageGenerator._assert_dtemplate_integrity(path, "SDE_ORA_JobDimension")

    def test_rewrite_rejects_reference_bin_without_class_info(self) -> None:
        sample_name = "OLD_TEMPLATE"
        target_name = "SDE_ORA_JobDimension"
        source = _dtemplate_bytes(sample_name, include_class_info=False)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / f"{target_name}.DTEMPLATE.zip"
            with self.assertRaisesRegex(ValueError, r"metadata\.\$\$classInfo"):
                self.generator._rewrite_sample_zip(
                    source,
                    output,
                    {sample_name: target_name},
                    self.generator._rewrite_dtemplate_member,
                    target_name,
                    self.ids,
                    self.now,
                )

    def test_assert_mtt_integrity_rejects_stale_short_description(self) -> None:
        stale = _mtt_bytes(
            "SDE_ORA_JobDimension",
            short_description="Session pushed from PC to ICS : JEG_SDE_IPCS_BItimePhasedDataBudget...",
            dtemplate_guid=self.ids.dtemplate,
            mtt_guid=self.ids.mtt,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "SDE_ORA_JobDimension.MTT.zip"
            path.write_bytes(stale)
            with self.assertRaisesRegex(ValueError, "shortDescription still references sample template"):
                IdmcExportPackageGenerator._assert_mtt_integrity(path, "SDE_ORA_JobDimension", self.ids)

    def test_runtime_parameters_are_rebuilt_from_remediated_xml(self) -> None:
        task = {
            "parameters": [
                {
                    "@type": "mtTaskParameter",
                    "id": 10,
                    "name": "$SQ_WC_PBCS_BUDGET_ACTUALS_FS$",
                    "type": "SOURCE",
                    "sourceObject": "DUMMY_SQ_WC_PBCS_BUDGET_ACTUALS_FS",
                    "runtimeParameterData": {"connectionParameterName": "Source"},
                },
                {
                    "@type": "mtTaskParameter",
                    "id": 11,
                    "name": "$WC_PBCS_BUDGET_ACTUALS_F$",
                    "type": "TARGET",
                    "targetObject": "WC_PBCS_BUDGET_ACTUALS_F",
                    "runtimeParameterData": {"connectionParameterName": "Target"},
                },
            ]
        }
        xml = """<POWERMART><REPOSITORY><FOLDER><MAPPING NAME="SIL_JobDimension">
            <INSTANCE NAME="W_JOB_DS" TYPE="SOURCE"/>
            <INSTANCE NAME="W_JOB_D" TYPE="TARGET"/>
        </MAPPING></FOLDER></REPOSITORY></POWERMART>"""

        with tempfile.TemporaryDirectory() as tmp:
            remediated = Path(tmp) / "remediated_xml"
            remediated.mkdir()
            (remediated / "SIL_JobDimension_remediated.xml").write_text(xml, encoding="utf-8")
            self.generator.remediated_folder = remediated

            self.generator._apply_mapping_runtime_parameters(task, "SIL_JobDimension", self.ids)

        parameters = task["parameters"]
        self.assertEqual(["$W_JOB_DS$", "$W_JOB_D$"], [item["name"] for item in parameters])
        self.assertEqual(["SOURCE", "TARGET"], [item["type"] for item in parameters])
        self.assertEqual(f"@{self.ids.connection}", parameters[0]["sourceConnectionId"])
        self.assertEqual("W_JOB_D", parameters[1]["targetObject"])
        self.assertEqual("Source", parameters[0]["runtimeParameterData"]["connectionParameterName"])
        self.assertEqual("Target", parameters[1]["runtimeParameterData"]["connectionParameterName"])
        self.assertNotIn("WC_PBCS", json.dumps(parameters))
        self.assertEqual({}, parameters[0]["runtimeAttrs"])
        self.assertEqual({"INSERT": "YES"}, parameters[1]["runtimeAttrs"])

    def test_processor_marks_size_mismatch_invalid(self) -> None:
        broken = _dtemplate_bytes("SDE_ORA_JobDimension", declared_size=99999)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "SDE_ORA_JobDimension.DTEMPLATE.zip"
            path.write_bytes(broken)
            asset = IICSAsset(
                object_guid="g",
                object_name="SDE_ORA_JobDimension",
                object_type="DTEMPLATE",
                path="/Explore",
                file_path=path.name,
            )
            processor = IICSPackageProcessor(input_zip=path, output_dir=tmp)
            processor._validate_dtemplate(asset, path)
            self.assertFalse(asset.valid)
            self.assertTrue(any("fileRecord size mismatch" in issue for issue in asset.issues))

    def test_repair_package_fixes_size_and_mtt_metadata(self) -> None:
        package = io.BytesIO()
        with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "exportMetadata.v2.json",
                json.dumps({"name": "job-1", "sourceOrgId": "x", "exportedObjects": []}),
            )
            zf.writestr(
                "Explore/BIAINFADEV2_FLEX/Custom_Project/SDE_ORA_JobDimension.DTEMPLATE.zip",
                _dtemplate_bytes("SDE_ORA_JobDimension", declared_size=99999),
            )
            zf.writestr(
                "Explore/BIAINFADEV2_FLEX/Custom_Project/SDE_ORA_JobDimension.MTT.zip",
                _mtt_bytes(
                    "SDE_ORA_JobDimension",
                    short_description="Session pushed from PC to ICS : OLD_TEMPLATE_NAME",
                    dtemplate_guid="dt",
                    mtt_guid="mtt",
                ),
            )
            zf.writestr("exportPackage.chksum", "#\n")

        with tempfile.TemporaryDirectory() as tmp:
            input_zip = Path(tmp) / "broken.zip"
            output_zip = Path(tmp) / "fixed.zip"
            input_zip.write_bytes(package.getvalue())
            repair_export_package(input_zip, output_zip)

            with zipfile.ZipFile(output_zip) as zf:
                dt = zf.read("Explore/BIAINFADEV2_FLEX/Custom_Project/SDE_ORA_JobDimension.DTEMPLATE.zip")
                mtt = zf.read("Explore/BIAINFADEV2_FLEX/Custom_Project/SDE_ORA_JobDimension.MTT.zip")

            with zipfile.ZipFile(io.BytesIO(dt)) as dtz:
                record = json.loads(dtz.read("fileRecord.json").decode("utf-8"))[0]
                self.assertEqual(len(dtz.read("bin/@2.bin")), record["size"])

            with zipfile.ZipFile(io.BytesIO(mtt)) as mttz:
                task = json.loads(mttz.read("mtTask.json").decode("utf-8"))[0]
                self.assertIn("SDE_ORA_JobDimension", task["shortDescription"])
                self.assertNotIn("OLD_TEMPLATE_NAME", task["shortDescription"])

    def test_workflow_taskflow_rewrites_process_object_hyphen_names(self) -> None:
        sample_name = "JEG_SDE_ORA_PBCS_Actual_Proforma"
        sample_po = "JEG-SDE-ORA-PBCS-Actual-Proforma"
        target_name = "SDE_ORA_JobDimension"
        target_po = "SDE-ORA-JobDimension"
        sample_mtt = "oldMttGuid123456789012"
        taskflow_xml = f'''<aetgt:getResponse xmlns:aetgt="http://schemas.active-endpoints.com/appmodules/repository/2010/10/avrepository.xsd"
                   xmlns:types1="http://schemas.active-endpoints.com/appmodules/repository/2010/10/avrepository.xsd">
   <types1:Item>
      <types1:EntryId>old-entry</types1:EntryId>
      <types1:Name>{sample_name}</types1:Name>
      <types1:PublishedContributionId>project:/tf.{sample_name}/{sample_name}.tf.xml</types1:PublishedContributionId>
      <types1:Entry>
         <taskflow GUID="oldTf" displayName="{sample_name}" name="{sample_name}">
            <tempFields>
               <field name="{sample_name}" type="reference">
                  <options><option name="referenceTo">$po:{sample_po}</option></options>
               </field>
               <field name="INFA_CommandTask" type="reference">
                  <options><option name="referenceTo">$po:INFA-commandTask</option></options>
               </field>
            </tempFields>
            <flow id="a">
               <eventContainer id="c1">
                  <service id="s1">
                     <title>{sample_name}</title>
                     <serviceInput>
                        <parameter name="GUID" source="constant" updatable="true">{sample_mtt}</parameter>
                        <parameter name="Has Inout Parameters" source="constant" updatable="true">false</parameter>
                        <parameter name="taskField" source="nested">
                           <operation source="field" to="{sample_po}/taskProperties[1]/parameterFileDir">input.InputMappingTaskParameterFileDir</operation>
                        </parameter>
                     </serviceInput>
                     <serviceOutput>
                        <operation source="field" to="temp.{sample_name}/output/Run_Id">Run Id</operation>
                     </serviceOutput>
                  </service>
               </eventContainer>
            </flow>
            <dependencies>
               <processObject displayName="{sample_po}" name="{sample_po}">
                  <detail><field name="output" type="reference"/></detail>
               </processObject>
               <processObject displayName="INFA-commandTask" name="INFA-commandTask">
                  <detail><field name="output" type="reference"/></detail>
               </processObject>
            </dependencies>
         </taskflow>
      </types1:Entry>
   </types1:Item>
</aetgt:getResponse>'''
        assets = [{"name": target_name, "ids": self.ids}]
        templates = [
            {
                "name": sample_name,
                "dtemplate_id": "oldDt",
                "mtt_id": sample_mtt,
                "taskflow_id": "oldTf",
                "repo_handle": "old-entry",
                "workflow_templates": [
                    {
                        "name": sample_name,
                        "taskflow_id": "oldTf",
                        "repo_handle": "old-entry",
                        "taskflow_xml": taskflow_xml,
                    }
                ],
            }
        ]
        rewritten = self.generator._workflow_taskflow_xml(target_name, "newTfGuid", assets, templates, self.now)
        self.assertIn(f"$po:{target_po}", rewritten)
        self.assertIn(f'name="{target_po}"', rewritten)
        self.assertIn(f'displayName="{target_po}"', rewritten)
        self.assertIn(f"to=\"{target_po}/taskProperties", rewritten)
        self.assertNotIn(sample_po, rewritten)
        self.assertNotIn("INFA-commandTask", rewritten)
        self.assertIn(self.ids.mtt, rewritten)

    def test_single_service_taskflow_is_linearized(self) -> None:
        taskflow_xml = '''<flow id="a">
           <eventContainer id="svc">
              <service id="s1"><title>SIL_JobDimension</title></service>
              <link id="to_condition" targetId="condition"/>
           </eventContainer>
           <container id="condition" type="exclusive">
              <title>Link_Condition_condition</title>
              <flow id="branch"><link id="branch_link" targetId="c" type="containerLink"/></flow>
           </container>
           <end id="c"/>
        </flow>'''

        rewritten = self.generator._linearize_single_service_taskflow(taskflow_xml, "SIL_JobDimension")

        self.assertIn('targetId="c"', rewritten)
        self.assertNotIn('type="exclusive"', rewritten)
        self.assertNotIn("Link_Condition", rewritten)


if __name__ == "__main__":
    unittest.main()
