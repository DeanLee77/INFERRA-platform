# Governed Trigger Authoring Examples

These examples demonstrate the implemented AEGIS trigger feature described in `docs/INFERRA_Rule_Syntax_Dictionary.md`.

| File | Purpose |
|------|---------|
| `aegis_trigger_source_assessment.txt` | Source rule set that produces an outcome eligible to trigger downstream execution. |
| `aegis_trigger_target_eligibility.txt` | Target rule set started by the outcome-trigger policy. |
| `outcome_to_rule_set_policy.json` | Trigger policy for rule-set outcome to downstream rule-set execution. |
| `outcome_trigger_request.json` | Sample request body for `POST /api/v1/aegis/triggers/outcome`. |
| `direct_to_action_policy.json` | Trigger policy for direct event to governed action proposal. |
| `direct_trigger_request.json` | Sample request body for `POST /api/v1/aegis/triggers/direct`. |

The parent `authoring_catalog.json` file is the discovery entrypoint for authoring pages.
