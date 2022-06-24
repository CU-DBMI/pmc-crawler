# Center for Health AI - Software Engineering

For the month ending {{account['Month-ending Date']}}

Prepared {{account['Report Prepared Date']}}
## Account **{{account['Account/Client']}}**
{% for project in account['Projects'] -%}
### Project **{{project['Project Title']}}**
{% if project['Grant Proposal #'] -%}
Grant Proposal #: {{project['Grant Proposal #']}}
{% endif -%}
{% if project['Notes'] -%}
Notes: {{project['Notes']}}
{% endif -%}
{% for resource in project['Resources'] -%}
#### Tasks: {{resource['Resource']}}
|Task ID|Task|Notes|Complete Date|Hours
|---|---|---|---|---
{% for task in resource['Tasks'] -%}
|{{task['task_id']}}|{{task['Title']}}{% if task['Pull Request URL'] -%}<br>{{task['Pull Request URL']}}{% endif %}{% if task['Issue URL'] -%}<br>{{task['Issue URL']}}{% endif -%}|{{task['Notes']}}{% if['integration_state_rule'] -%}<br>_{{task['integration_state_rule']}}_{% endif %}|{{task['task_end_date']}}|{{task['Hours']}}
{% endfor -%}
|   |   |   |Subtotal Task Hours|**{{resource['Completed Hours']}}**
{% endfor -%}
|   |{{project['Project Title']}}|   |Total Project Hours|**{{project['Completed Hours']}}**
{% endfor -%}
|   |{{account['Account/Client']}}|   |Total Account Hours|**{{account['Completed Hours']}}**

## Notes
1. `hours_split_between_owners` indicates more than one resource worked on a task; hours are split between the resources.
2. `hours_from_session_records` indicates a complex task broken into 1 or more work sessions; only the final task completed date is shown.

Report v1.1