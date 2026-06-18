# Day 5 Complexity Classification Report

## Rule-Based Mapping Complexity

| XML | Mapping | Transformation Count | Complexity | Score | Reason |
|---|---|---:|---|---:|---|
| JEG_SDE_IPCS_BItimePhasedDataBudgetFact.XML | JEG_SDE_IPCS_BItimePhasedDataBudgetFact | 2 | Medium | 40 | <5 transformations, SQL override, Expression logic |
| JEG_SDE_ORA_PBCS_Actual_Proforma.XML | JEG_SDE_ORA_PBCS_Actual_Proforma | 2 | Medium | 40 | <5 transformations, SQL override, Expression logic |
| JEG_SDE_ORA_PBCS_Actual_SM.XML | JEG_SDE_ORA_PBCS_Actual_SM | 2 | Simple | 20 | <5 transformations, Expression logic |
| JEG_SDE_ORA_WC_PBCS_BUDGET_ACTUALS_FS.XML | JEG_SDE_ORA_WC_PBCS_BUDGET_ACTUALS_FS | 2 | Medium | 40 | <5 transformations, SQL override, Expression logic |
| JEG_SDE_POL_ProjectReviewSubmittedDimensionStage.XML | JEG_SDE_POL_ProjectReviewSubmittedDimensionStage | 2 | Simple | 20 | <5 transformations, Expression logic |
| JEG_SIL_IPCS_BITimephaseDataBudgetFact.XML | JEG_SIL_IPCS_BItimePhaseDataBudgetFact | 6 | Complex | 100 | 5-10 transformations, Lookup exists, SQL override, Expression logic, Router/Filter, Nested/multiple mapplets |
| JEG_SIL_WC_PBCS_BUDGET_ACTUALS_F.XML | JEG_SIL_WC_PBCS_BUDGET_ACTUALS_F | 2 | Medium | 40 | <5 transformations, SQL override, Expression logic |
| SDE_EmployeeHeadCount.XML | JEG_SDE_ORA_TRUNCATE_DIM | 1 | Medium | 31 | <5 transformations, SQL override |
| SDE_EmployeeHeadCount.XML | SDE_EmployeeHeadCount1 | 22 | Complex | 95 | >10 transformations, Lookup exists, SQL override, Expression logic, Mapplet |
| SDE_EmployeeHeadCount.XML | SDE_EmployeeHeadCount2 | 20 | Complex | 95 | >10 transformations, Lookup exists, SQL override, Expression logic, Mapplet |
| SDE_ORA_EmployeeDimension.XML | SDE_ORA_EmployeeDimension | 2 | Medium | 45 | <5 transformations, Expression logic, Nested/multiple mapplets |
| SDE_ORA_ProjectCostLine.XML | JEG_SDE_ORA_ProjectCostLineFact_Elim | 2 | Medium | 45 | <5 transformations, Expression logic, Nested/multiple mapplets |
| SDE_ORA_ProjectCostLine.XML | JEG_SDE_ORA_ProjectCostLineFact_Elim_Hub | 2 | Medium | 45 | <5 transformations, Expression logic, Nested/multiple mapplets |
| SDE_ORA_ProjectCostLine.XML | JEG_SDE_ORA_ProjectCostLineFact_IC | 2 | Medium | 45 | <5 transformations, Expression logic, Nested/multiple mapplets |
| SDE_ORA_ProjectCostLine.XML | JEG_SDE_ORA_ProjectCostLineFact_IC_HUB | 2 | Medium | 45 | <5 transformations, Expression logic, Nested/multiple mapplets |
| SDE_ORA_ProjectCostLine.XML | JEG_SDE_ORA_ProjectCostLineFact_NL | 2 | Medium | 45 | <5 transformations, Expression logic, Nested/multiple mapplets |
| SDE_ORA_ProjectCostLine.XML | JEG_SDE_ORA_TRUNCATE_DIM | 1 | Medium | 31 | <5 transformations, SQL override |
| SDE_ORA_ProjectCostLine.XML | SDE_ORA_ProjectCostLineFact | 2 | Medium | 45 | <5 transformations, Expression logic, Nested/multiple mapplets |
| SDE_ORA_ProjectCostLine.XML | SDE_ORA_ProjectCostLineFact_PCC | 2 | Medium | 45 | <5 transformations, Expression logic, Nested/multiple mapplets |
| SIL_EmployeeDimension.XML | SIL_EmployeeDimension | 6 | Complex | 100 | 5-10 transformations, Lookup exists, SQL override, Expression logic, Router/Filter, Nested/multiple mapplets |
| SIL_EmployeeDimension_SCDUpdate.XML | SIL_EmployeeDimension_SCDUpdate | 4 | Medium | 65 | <5 transformations, Lookup exists, SQL override, Expression logic, Router/Filter |
| SIL_EmployeeHeadCount.XML | SIL_EmployeeHeadCount | 10 | Complex | 100 | 5-10 transformations, Lookup exists, SQL override, Expression logic, Router/Filter, Mapplet |
| SIL_ProjectCostLine_Fact.XML | SIL_ProjectCostLine_Fact | 7 | Complex | 100 | 5-10 transformations, Lookup exists, SQL override, Expression logic, Router/Filter, Nested/multiple mapplets |

## Scoring Rules

| Signal | Score Impact |
|---|---:|
| Transformation count 5-10 | +20 |
| Transformation count >10 | +25 |
| Lookup exists | +15 |
| SQL override exists | +20 |
| SQL override minimum band | Medium |
| Expression logic exists | +10 |
| Router or Filter exists | +10 |
| Stored Procedure exists | +20 |
| Mapplet exists | +15 |
| Nested/multiple mapplets exist | +25 |
| Aggregator, Joiner, Union, or Sequence Generator exists | +15 each |

Complexity bands: Simple = 1-30, Medium = 31-70, Complex = 71-100.
