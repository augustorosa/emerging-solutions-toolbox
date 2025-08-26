import streamlit as st
import pandas as pd
import altair as alt
import json
import time

from src.Page import Page
from src.tools import sql_to_dataframe,sql_to_pandas
from snowflake.snowpark.context import get_active_session

class table_metrics(Page):
    
    def __init__(self):
        self.name = "table_metrics"

    def print_page(self):



        session = st.session_state.session


        col_h1, col_h2, col_h3 = st.columns([8,1,1])
        col_h1.subheader('Data Metrics Monitoring')
        if col_h3.button('↻'):
                st.rerun()

        with st.expander("Raw Results"):
                try:
                    dmf_results = session.sql("SELECT * FROM SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS").to_pandas()
                    st.dataframe(dmf_results)
                except Exception:
                    dmf_results = pd.DataFrame()
                    st.info("DATA_QUALITY_MONITORING_RESULTS is not accessible. Ensure your account has the DMFs/Expectations feature and role has SELECT on SNOWFLAKE.LOCAL.")

        t1,t2,t3 = st.tabs(("Metrics Monitoring","Metric Scan Results","Expectations"))
        with t1:
            col1, col2, col3 = st.columns([1,1,1])

            def LOAD_RECENT_METRICS():
                METRICS_QUERY = """
                    with LATEST_METRIC as (
                        select
                            METRIC_NAME as QUALITY_CHECK,
                            TABLE_SCHEMA,
                            TABLE_NAME,
                            ARGUMENT_NAMES,
                            max(MEASUREMENT_TIME) as LATEST_MEASUREMENT_TIME,
                            array_agg(VALUE) within group (order by MEASUREMENT_TIME) as VALUE_HISTORY
                        from
                            SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS 
                        where
                            timediff(day, MEASUREMENT_TIME, current_timestamp()) < 30
                        group by
                            TABLE_SCHEMA,
                            TABLE_NAME,
                            QUALITY_CHECK,
                            ARGUMENT_NAMES
                    )
                    select
                        case when D.METRIC_DATABASE = 'SNOWFLAKE' then concat('❄️ ', L.QUALITY_CHECK)
                                when D.METRIC_DATABASE != 'SNOWFLAKE' then concat('💼 ', L.QUALITY_CHECK)
                        end as DMF_NAME,
                        L.TABLE_SCHEMA||'.'||L.TABLE_NAME as TABLE_NAME,
                        L.ARGUMENT_NAMES,
                        case when D.VALUE > 0 then concat('🚨 ', D.VALUE)
                                when D.VALUE = 0 then concat('✅ ', D.VALUE)
                        end as ISSUES_FOUND,
                        L.VALUE_HISTORY,
                        concat(to_char(convert_timezone('Europe/Berlin', D.MEASUREMENT_TIME), 'YYYY-MM-DD at HH:MI:SS'),' (',(timediff(minute, D.MEASUREMENT_TIME, current_timestamp())),' minutes ago)') as LAST_MEASURED
                    from
                        LATEST_METRIC L
                    join
                        SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS  D
                        on  L.TABLE_NAME = D.TABLE_NAME
                        and L.TABLE_SCHEMA = D.TABLE_SCHEMA
                        and L.QUALITY_CHECK = D.METRIC_NAME
                        and L.LATEST_MEASUREMENT_TIME = D.MEASUREMENT_TIME
                    order by
                        LAST_MEASURED desc
                    """
                
                METRICS = session.sql(METRICS_QUERY).collect()
                METRICS_DF = pd.DataFrame(METRICS)
                
                return METRICS_DF


            # Load the DataFrame
            try:
                METRICS_DF = LOAD_RECENT_METRICS()
            except Exception:
                METRICS_DF = pd.DataFrame()
                st.info("Recent metrics are unavailable. Check access to SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS and that DMFs are running.")

            # Function to add 'ALL' option to the unique values list
            def add_all_option(unique_values):
                return ['All'] + unique_values.tolist()


            # Create multiselect widgets for each column with 'ALL' option
            if len(METRICS_DF) > 0:
                dmf_name_options = add_all_option(METRICS_DF['DMF_NAME'].unique())
                dmf_table_options = add_all_option(METRICS_DF['TABLE_NAME'].unique())

            else:
                dmf_name_options = []
                dmf_table_options = []

            dmf_name_filter = col1.selectbox('DMF', options=dmf_name_options, placeholder='All')
            dmf_table_filter = col2.selectbox('Table', options=dmf_table_options, placeholder='All')
            issues_found_filter = col3.selectbox('Expectations', options= ['Failed', 'All'])


            def filter_dataframe(df, dmf_name_filter, dmf_table_filter, issues_found_filter):
                if len(df) > 0:
                    if dmf_name_filter != 'All':
                        df = df[df['DMF_NAME'] == dmf_name_filter]
                        
                    if dmf_table_filter != 'All':
                        df = df[df['TABLE_NAME'] == dmf_table_filter]
                        
                    if issues_found_filter == 'Failed':
                        df = df[df['ISSUES_FOUND'] != '✅ 0']
                    elif issues_found_filter == 'All':
                        df = df
                return df
                
            FILTERED_DF = filter_dataframe(METRICS_DF, dmf_name_filter, dmf_table_filter, issues_found_filter)


            st.subheader('') #just to add some space

            METRICS_COUNTER = session.sql("""
                with LATEST_METRIC as (
                        select
                            METRIC_NAME as QUALITY_CHECK,
                            TABLE_SCHEMA||'.'||TABLE_NAME as TABLE_NAME,
                            ARGUMENT_NAMES,
                            max(MEASUREMENT_TIME) as LATEST_MEASUREMENT_TIME
                        from
                            SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS 
                        where
                            timediff(day, MEASUREMENT_TIME, current_timestamp()) < 14
                        group by
                            TABLE_NAME,
                            TABLE_SCHEMA,
                            QUALITY_CHECK,
                            ARGUMENT_NAMES
                    ),
                    LATEST_VALUE as(
                        select
                            D.VALUE as VALUE,
                            L.TABLE_NAME
                        from
                            LATEST_METRIC L
                        join
                            SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS  D
                            on  L.TABLE_NAME = D.TABLE_SCHEMA||'.'||D.TABLE_NAME
                            and L.QUALITY_CHECK = D.METRIC_NAME
                            and L.LATEST_MEASUREMENT_TIME = D.MEASUREMENT_TIME
                    )
                select 
                    count(*) as ALL_METRICS,
                    (select count(*) from LATEST_VALUE where VALUE > 0) as FAILED_METRICS,
                    (select count(*) from LATEST_VALUE where VALUE = 0) as OKAY_METRICS,
                    (select count(distinct TABLE_NAME) from LATEST_VALUE where VALUE > 0) as FAILED_TABLES
                from
                    LATEST_VALUE
                """).collect()
            FAILED_METRICS = str(METRICS_COUNTER[0].FAILED_METRICS)
            OKAY_METRICS = str(METRICS_COUNTER[0].OKAY_METRICS)
            FAILED_TABLES = str(METRICS_COUNTER[0].FAILED_TABLES)

            col_m1, col_m2, col_m3 = st.columns([1,1,1])

            col_m1.metric("Failed expectations", '🚨 '+FAILED_METRICS)
            col_m2.metric("Tables failing expectations", '⌗ '+FAILED_TABLES)
            col_m3.metric("Met expectations", '✅ '+OKAY_METRICS)

            st.subheader('') #just to add some space


            ALL_METRICS_HISTOGRAM = session.sql("""
                select
                    count(distinct case when VALUE != 0 then METRIC_NAME || '|' || TABLE_ID || '|' || to_varchar(ARGUMENT_IDS) end) as FAILED_METRICS,
                    count(distinct case when VALUE  = 0 then METRIC_NAME || '|' || TABLE_ID || '|' || to_varchar(ARGUMENT_IDS) end) as SUCCEEDED_METRICS,
                    date_trunc(hour,MEASUREMENT_TIME) as HOUR
                from
                    SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS 
                where
                    timediff(day, MEASUREMENT_TIME, current_timestamp()) < 7
                group by
                    HOUR
                order by
                    HOUR desc
            """).to_pandas()
                
            MELTED_DF = ALL_METRICS_HISTOGRAM.melt('HOUR', var_name='RESULT', value_name='COUNTER')
                
            CHART = alt.Chart(MELTED_DF).mark_bar(size=5).encode(
                    x=alt.X('HOUR:T', axis=alt.Axis(title='Distinct Quality Checks per hour')), 
                    y=alt.Y('COUNTER:Q', axis=alt.Axis(title=None)), 
                    color=alt.Color('RESULT:N', legend=None,
                            scale=alt.Scale(domain=['FAILED_METRICS', 'SUCCEEDED_METRICS'], range=['#FF0000', '#008000']))
                    ).properties(height=240)

            st.altair_chart(CHART, use_container_width=True)



            st.dataframe(FILTERED_DF,
                        column_config={
                            "VALUE_HISTORY": st.column_config.AreaChartColumn("Checks (last 14 days)", y_min=0),
                            "ARGUMENT_NAMES": st.column_config.ListColumn("Columns")
                        },
                            hide_index= True, use_container_width=True)


            with st.expander('Show Metrics History'):
                METRICS_HISTORY = session.sql("""
                    select
                        to_char(convert_timezone('Europe/Berlin', MEASUREMENT_TIME), 'YYYY-MM-DD at HH:MI:SS') as MEASUREMENT_TIME,
                        case when METRIC_DATABASE = 'SNOWFLAKE' then concat('❄️ ', METRIC_NAME)
                                when METRIC_DATABASE != 'SNOWFLAKE' then concat('💼 ', METRIC_NAME)
                        end as METRIC_NAME,
                        VALUE,
                        TABLE_NAME,
                        ARGUMENT_NAMES,
                        TABLE_SCHEMA
                    from 
                        SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS 
                    order by 
                        MEASUREMENT_TIME desc 
                    limit 100
                    """).collect()
                st.dataframe(METRICS_HISTORY, hide_index= True, use_container_width=True)



            st.divider()

        with t2:

            allowed_metrics = [
            "NULL_COUNT",
            "NULL_PERCENT",
            "BLANK_COUNT",
            "BLANK_PERCENT",
            "DUPLICATE_COUNT"]

            def data_metric_scan(table,metric,column):
                return session.sql(f"""
                SELECT *
                  FROM TABLE(SYSTEM$DATA_METRIC_SCAN(
                    REF_ENTITY_NAME  => '{table}',
                    METRIC_NAME  => 'snowflake.core.{metric}',
                    ARGUMENT_NAME => '{column}'
                  ));
                """).collect()



            try:
                tables = dmf_results["TABLE_NAME"].unique()
            except Exception:
                tables = []
            chosen_table = st.selectbox("Select Table", tables)
            if chosen_table:
                active = True
                scheduled_metrics = dmf_results[dmf_results["TABLE_NAME"]==chosen_table]["METRIC_NAME"].unique()
                schema = dmf_results[dmf_results["TABLE_NAME"]==chosen_table]["TABLE_SCHEMA"].unique()[0]
                database = dmf_results[dmf_results["TABLE_NAME"]==chosen_table]["TABLE_DATABASE"].unique()[0]
                table_path = f'{database}.{schema}.{chosen_table}'
                scheduled_metrics = [metric for metric in scheduled_metrics if metric in allowed_metrics]
                
                chosen_metric = st.selectbox("Select Metric",scheduled_metrics)
                if chosen_metric:
                    metric_columns = dmf_results[(dmf_results["TABLE_NAME"]==chosen_table) & (dmf_results["METRIC_NAME"]==chosen_metric)]["ARGUMENT_NAMES"].unique()
                    metric_columns = metric_columns.tolist()
                    for index,metric in enumerate(metric_columns):
                        metric_columns[index] = json.loads(metric)
                    metric_columns = sum(metric_columns,[])
                    chosen_column = st.selectbox("Select Column",metric_columns)
                    if st.button("Run"):
                        offending_rows = data_metric_scan(table_path,chosen_metric,chosen_column)
                        if len(offending_rows) == 0:
                            st.success("No Violating Rows")
                        else:
                            st.error(f"{len(offending_rows)} Found")
                            st.dataframe(offending_rows)

        with t3:
            st.subheader("Evaluate expectations now")
            # Reuse tables from dmf_results if available; otherwise, allow manual input
            try:
                tables = dmf_results["TABLE_NAME"].unique()
                schema_lookup = dmf_results.set_index("TABLE_NAME")["TABLE_SCHEMA"].to_dict()
                db_lookup = dmf_results.set_index("TABLE_NAME")["TABLE_DATABASE"].to_dict()
            except Exception:
                tables = []
                schema_lookup = {}
                db_lookup = {}

            manual_db, manual_schema, manual_table = st.columns(3)
            selected_table = st.selectbox("Select Table (from scheduled metrics)", options=tables if len(tables) > 0 else [], placeholder="Choose...")
            if selected_table:
                sel_db = db_lookup.get(selected_table, "")
                sel_schema = schema_lookup.get(selected_table, "")
            else:
                sel_db = manual_db.text_input("Database")
                sel_schema = manual_schema.text_input("Schema")
                selected_table = manual_table.text_input("Table")

            if sel_db and sel_schema and selected_table:
                table_path = f"{sel_db}.{sel_schema}.{selected_table}"
                if st.button("Evaluate Expectations", type="primary"):
                    try:
                        eval_df = session.sql(f"SELECT * FROM TABLE(SYSTEM$EVALUATE_DATA_QUALITY_EXPECTATIONS(REF_ENTITY_NAME => '{table_path}'))").to_pandas()
                        if len(eval_df) == 0:
                            st.success("No expectations found or no violations at this time.")
                        else:
                            st.dataframe(eval_df, use_container_width=True)
                    except Exception as e:
                        st.warning("Could not evaluate expectations. Ensure privileges and Enterprise features are enabled.")

            st.divider()
            st.subheader("Expectation status (read-only)")
            st.caption("Showing recent expectation evaluations from SNOWFLAKE.LOCAL if available")
            # Try the expectation status view first; fallback to RAW table if needed
            try:
                exp_status = session.sql(
                    """
                    select 
                        TABLE_DATABASE, TABLE_SCHEMA, TABLE_NAME,
                        METRIC_NAME,
                        ARGUMENT_NAMES,
                        EXPECTATION_NAME,
                        EXPECTATION_EXPRESSION,
                        MEASUREMENT_TIME,
                        VIOLATED
                    from SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_EXPECTATION_STATUS
                    where timediff(day, MEASUREMENT_TIME, current_timestamp()) < 14
                    order by MEASUREMENT_TIME desc
                    """
                ).to_pandas()
                st.dataframe(exp_status, use_container_width=True)
            except Exception:
                try:
                    raw = session.sql(
                        """
                        select 
                          resource_attributes:object_database::string as TABLE_DATABASE,
                          resource_attributes:object_schema::string as TABLE_SCHEMA,
                          resource_attributes:object_name::string as TABLE_NAME,
                          resource_attributes:metric_name::string as METRIC_NAME,
                          resource_attributes:argument_names::string as ARGUMENT_NAMES,
                          resource_attributes:expectation_name::string as EXPECTATION_NAME,
                          resource_attributes:expectation_expression::string as EXPECTATION_EXPRESSION,
                          measurement_time as MEASUREMENT_TIME,
                          value::boolean as VIOLATED
                        from SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS_RAW
                        where resource_attributes:snow.data_metric.record_type::string = 'EXPECTATION_VIOLATION_STATUS'
                          and timediff(day, MEASUREMENT_TIME, current_timestamp()) < 14
                        order by MEASUREMENT_TIME desc
                        """
                    ).to_pandas()
                    st.dataframe(raw, use_container_width=True)
                except Exception:
                    st.info("Expectation status views are not accessible. Ensure account has Enterprise features and required privileges.")
    def print_sidebar(self):
        pass