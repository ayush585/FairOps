# FairOps BI Guide — Looker Studio Dashboard

To provide full observability to compliance and legal units, we utilize **Google Looker Studio**. FairOps is designed natively to emit structured data directly to Google BigQuery, making dashboard integration seamless.

Here is how to set up the dashboard.

## 1. Connect the Data Source

1. Open Looker Studio (`lookerstudio.google.com`).
2. Add a new **Data Source** -> Select **BigQuery**.
3. Point to your Project -> Dataset `fairops_metrics` -> Table `bias_audits`.

## 2. Model Fairness Scorecard (Gauge Charts)

Build gauges to immediately reflect the `overall_severity` of the latest audit.

- **Data Source**: `bias_audits`
- **Chart Type**: Gauge
- **Metric**: Record Count (filtered to latest)
- **Filters**: 
  - Since `overall_severity` is a string, construct a calculated field:
    ```sql
    CASE
      WHEN overall_severity = 'CRITICAL' THEN 4
      WHEN overall_severity = 'HIGH' THEN 3
      WHEN overall_severity = 'MEDIUM' THEN 2
      WHEN overall_severity = 'LOW' THEN 1
      ELSE 0
    END
    ```
- **Styling**: Set Gauge bounds to map to FairOps RAG Colors (Red at 4, Green at 0).

## 3. Temporal Trend View (Line Chart)

Track fairness degrading over time before mitigation interventions kick in.

- **Data Source**: `bias_audits`
- **Chart Type**: Time series chart
- **Dimension**: `audit_timestamp`
- **Metric**: Parse out the core metrics out of the JSON string `metrics` payload. Create a blended metric called `Extracted Disparate Impact`.
    ```sql
    CAST(JSON_EXTRACT_SCALAR(metrics, '$.disparate_impact_ratio.value') AS FLOAT64)
    ```
- **Reference Line**: Add a static horizontal line at `0.80` to represent the EEOC 4/5ths Rule threshold.

## 4. Demographic Slice Drill-Down (Bar Chart)

Compare performance against population intersection.

- **Data Source**: Re-connect to BQ, but utilize BigQuery's `UNNEST` command to flatten the demographic slices array so Looker can map it:
    ```sql
    SELECT 
      audit_id, 
      JSON_EXTRACT_SCALAR(slice, '$.attribute') as attribute,
      JSON_EXTRACT_SCALAR(slice, '$.group_value') as group_value,
      CAST(JSON_EXTRACT_SCALAR(slice, '$.positive_rate') AS FLOAT64) as pos_rate
    FROM `fairops_metrics.bias_audits`,
    UNNEST(JSON_EXTRACT_ARRAY(demographic_slices)) as slice
    ```
- **Chart Type**: Bar Chart
- **Dimension**: `group_value`
- **Metric**: `pos_rate`

## 5. Mitigation Event Overlay

Anytime a model undergoes mitigation (tracked in Spanner and emitted), a vertical annotation line should intersect the Temporal Line Graph, demonstrating the success of algorithmic un-biasing visually.
