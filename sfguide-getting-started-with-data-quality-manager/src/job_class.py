import streamlit as st
import snowflake.snowpark.functions as F

from snowflake.snowpark import types as T
from src.tools import toggle_button, get_tables, get_schemas, get_anomaly_chart, change_page, print_nsc_results, pag_up, pag_down, sql_to_dataframe, sql_to_pandas
from src.globals import APP_OPP_DB, APP_CONFIG_SCHEMA, APP_TEMP_DATA_SCHEMA, APP_RESULTS_SCHEMA, APP_DATA_SCHEMA, dates_chron_dict, reverse_chron_dict
class Job:
    def __init__(self, note, job_info,i,emoji_flag):
        self.note_id = note[0]
        self.Job_id = note[1]
        self.run_time = note[2]
        self.count = note[3]
        self.table = note[4]
        self.alert_flag = note[5]
        self.type = note[6]
        self.read = note[7]
        self.i = i
        self.emoji_flag = emoji_flag
        self.job_name = list(job_info[job_info["JOB_ID"] == self.Job_id]["JOB_NAME"])[0] if len(list(job_info[job_info["JOB_ID"] == self.Job_id]["JOB_NAME"])) > 0 else "No Job Name"
        self.print_job()
    
    def read_all_notes(self,notes):
        for note in notes:
            id = note[0]
            read = note[7]
            type = note[6]
            if read is 'pending review':
                self.read_note(id,type)
    
    def read_note(self,note_id, note_type):
        session = st.session_state.session
        if note_type == 'ANOMOLY':
            sql_str = f"UPDATE {APP_OPP_DB}.{APP_RESULTS_SCHEMA}.DQ_ANOMALY_DETECT_RESULTS SET ALERT_STATUS = 'READ' WHERE (JOB_ID||'_'||RUN_DATETIME) = '{note_id}'"
        elif note_type == 'NON-STAT':
            sql_str = f"UPDATE {APP_OPP_DB}.{APP_RESULTS_SCHEMA}.DQ_NON_STAT_CHECK_RESULTS SET ALERT_STATUS = 'READ' WHERE (JOB_ID||'_'||RUN_DATETIME) = '{note_id}'"
        elif note_type == 'SNOWFLAKE_DMF':
            sql_str = f"UPDATE {APP_OPP_DB}.{APP_RESULTS_SCHEMA}.DQ_SNOWFLAKE_DMF_RESULTS SET ALERT_STATUS = 'READ' WHERE (JOB_ID||'_'||RUN_DATETIME) = '{note_id}'"
        sql_to_dataframe(sql_str)

    def save_edits(self, df, table):

        session = st.session_state.session

        t = session.table(table).filter(F.col("ALERT_FLAG") == 1)

        df = df[df["COMMENTS"].notnull()]

        if "RECORD_IDS" in df.columns:

            t_new = session.createDataFrame(df).with_column("RECORD_IDS",
                                                            F.parse_json(F.col("RECORD_IDS")).cast(T.VariantType()))
            session.table(table).merge(
                t_new,
                ((t['JOB_ID'] == t_new['JOB_ID']) &
                 (t['RUN_DATETIME'] == t_new['RUN_DATETIME']) &
                 (t['CHECK_TYPE_ID'] == t_new['CHECK_TYPE_ID']) &
                 (t['RECORD_IDS'] == t_new['RECORD_IDS'])),
                [
                    F.when_matched().update(
                        {"COMMENTS": t_new["COMMENTS"]}
                    )
                ]
            )

        else:
            t_new = session.createDataFrame(df).with_column("PARTITION_VALUES",
                                                            F.parse_json(F.col("PARTITION_VALUES")).cast(T.ArrayType()))
            session.table(table).merge(
                t_new,
                ((t['JOB_ID'] == t_new['JOB_ID']) &
                 (t['RUN_DATETIME'] == t_new['RUN_DATETIME']) &
                 (t['CHECK_TYPE_ID'] == t_new['CHECK_TYPE_ID']) &
                 (t['PARTITION_VALUES'] == t_new['PARTITION_VALUES'])),
                [
                    F.when_matched().update(
                        {"COMMENTS": t_new["COMMENTS"]}
                    )
                ]
            )
    def print_job(self):
        session = st.session_state.session
        description, button1, button2 = st.columns((19, 2, 2))
        description.subheader(f"**{self.job_name}**")
        description.write(self.run_time)

        button1.write("#")
        if (self.read == 'pending review'):
            button1.button("Mark as read", type="primary", key="mark read" + str(self.note_id), on_click=self.read_note,
                           args=(self.note_id, self.type))
        else:
            button1.write(" ")
        button2.write("#")
        if "show_flag" + str(self.note_id) not in st.session_state:
            st.session_state["show_flag" + str(self.note_id)] = False
        button2.button("Show more", key="show" + str(self.note_id) + str(self.i), on_click=toggle_button,
                       args=("show_flag" + str(self.note_id),))

        # st.write(st.session_state["show_flag"+str(self.note_id)])
        if self.type == "ANOMOLY":
            if self.emoji_flag:
                if self.alert_flag == 0:
                    message = ':white_check_mark: ***No Alerts for run***'
                elif self.alert_flag == 1:
                    message = f':x: ***{self.count} anomilies found in {self.table}***'
            else:
                message = f'***{self.count} anomilies found in {self.table}***'
            description.write(f"{message}")
            if (st.session_state["show_flag" + str(self.note_id)]):
                df = sql_to_dataframe(
                    f"SELECT * FROM {APP_OPP_DB}.{APP_RESULTS_SCHEMA}.DQ_ANOMALY_DETECT_RESULTS WHERE (JOB_ID||'_'||RUN_DATETIME) = '{self.note_id}' AND ALERT_FLAG=1")
                # df['PARTITION_VALUES'] = df["PARTITION_VALUES"].asself.type('string').replace('\\[','')
                # df['PARTITION_STR'] = [row["PARTITION_VALUES"].split(',') for index,row in df.iterrows()]
                edited_df = st.data_editor(df, key="editdf" + str(self.note_id) + str(self.i))
                st.button("Save", type='primary', on_click=self.save_edits,
                          args=(edited_df, f'{APP_OPP_DB}.{APP_RESULTS_SCHEMA}.DQ_ANOMALY_DETECT_RESULTS'),
                          key="save_btn" + str(self.note_id) + str(self.i))
                with st.expander("Results"):
                    get_anomaly_chart(f"{APP_OPP_DB}.{APP_RESULTS_SCHEMA}.DQ_ANOMALY_DETECT_RESULTS", self.note_id, 1)
        
        elif self.type == 'NON-STAT':
            if self.emoji_flag:
                if self.alert_flag == 0:
                    message = ':white_check_mark: ***No Alerts for run***'
                elif self.alert_flag == 1:
                    message = f':x: ***{self.count} alerts found in {self.table}***'
            else:
                message = f'***{self.count} alerts found in {self.table}***'
            description.write(f"{message}")
            if (st.session_state["show_flag" + str(self.note_id)]):
                df = sql_to_dataframe(
                    f"SELECT * FROM {APP_OPP_DB}.{APP_RESULTS_SCHEMA}.DQ_NON_STAT_CHECK_RESULTS WHERE (JOB_ID||'_'||RUN_DATETIME) = '{self.note_id}' AND ALERT_FLAG=1")
                # df['PARTITION_STR'] = [row["PARTITION_VALUES"].split(',') for index,row in df.iterrows()]
                edited_df = st.data_editor(df, key="editdf" + str(self.note_id) + str(self.i))
                description.write(f'Table impacted: {self.table}')
                st.button("Save", type='primary', on_click=self.save_edits,
                          args=(edited_df, f'{APP_OPP_DB}.{APP_RESULTS_SCHEMA}.DQ_NON_STAT_CHECK_RESULTS'),
                          key="save_btn" + str(self.note_id) + str(self.i))
                with st.expander("Results"):
                    print_nsc_results(f"{APP_OPP_DB}.{APP_RESULTS_SCHEMA}.DQ_NON_STAT_CHECK_RESULTS", self.note_id, 1)

        elif self.type == 'SNOWFLAKE_DMF':
            if self.emoji_flag:
                if self.alert_flag == 0:
                    message = ':white_check_mark: ***No Alerts for run***'
                elif self.alert_flag == 1:
                    message = f':x: ***{self.count} alerts found***'
            else:
                message = f'***{self.count} alerts found***'
            description.write(f"{message}")
            if (st.session_state["show_flag" + str(self.note_id)]):
                df = sql_to_dataframe(
                    f"SELECT * FROM {APP_OPP_DB}.{APP_RESULTS_SCHEMA}.DQ_SNOWFLAKE_DMF_RESULTS WHERE (JOB_ID||'_'||RUN_DATETIME) = '{self.note_id}' AND ALERT_FLAG=1")
                # df['PARTITION_STR'] = [row["PARTITION_VALUES"].split(',') for index,row in df.iterrows()]
                edited_df = st.data_editor(df, key="editdf" + str(self.note_id) + str(self.i))
                description.write(f'Table impacted: {self.table}')
                st.button("Save", type='primary', on_click=self.save_edits,
                          args=(edited_df, f'{APP_OPP_DB}.{APP_RESULTS_SCHEMA}.DQ_SNOWFLAKE_DMF_RESULTS'),
                          key="save_btn" + str(self.note_id) + str(self.i))
        elif self.type == 'EXPECTATION':
            # Expectation violations sourced from SNOWFLAKE.LOCAL views/RAW (read-only)
            if self.emoji_flag:
                if self.alert_flag == 0:
                    message = ':white_check_mark: ***No expectation violations***'
                elif self.alert_flag == 1:
                    message = f':x: ***{self.count} expectation violations***'
            else:
                message = f'***{self.count} expectation violations***'
            description.write(f"{message}")
            if (st.session_state["show_flag" + str(self.note_id)]):
                # Attempt to show detailed expectation status for the table and time
                try:
                    exp_df = sql_to_dataframe(
                        f"""
                        select 
                            TABLE_DATABASE, TABLE_SCHEMA, TABLE_NAME,
                            METRIC_NAME, ARGUMENT_NAMES,
                            EXPECTATION_NAME, EXPECTATION_EXPRESSION,
                            MEASUREMENT_TIME, VIOLATED
                        from SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_EXPECTATION_STATUS
                        where (TABLE_SCHEMA||'.'||TABLE_NAME) = '{self.table}'
                          and MEASUREMENT_TIME = '{self.run_time}'
                        order by METRIC_NAME
                        """
                    )
                    st.dataframe(exp_df, use_container_width=True)
                except Exception:
                    try:
                        raw_df = sql_to_dataframe(
                            f"""
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
                              and (resource_attributes:object_schema::string||'.'||resource_attributes:object_name::string) = '{self.table}'
                              and measurement_time = '{self.run_time}'
                            order by METRIC_NAME
                            """
                        )
                        st.dataframe(raw_df, use_container_width=True)
                    except Exception:
                        st.info("Cannot load expectation details. Ensure SNOWFLAKE.LOCAL views are accessible.")