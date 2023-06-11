import os

from sqlalchemy import create_engine
from garminconnect import Garmin

from garmin_collectors import *

def get_cockroachdb_conn():
    os.system('mkdir -p /tmp/.postgresql')
    os.system('chmod +rw /tmp/.postgresql')
    os.system('curl -o /tmp/.postgresql/root.crt -O ' + os.environ.get('cockroachdb_cert'))

    # Init connection to CockroachDB
    connection_string = os.environ.get('cockroachdb')
    connection_string = connection_string.replace('database_name', 'garmin')

    engine = create_engine(
        connection_string,
        connect_args={
        #     'ssl':{
                'sslrootcert': '/tmp/.postgresql/root.crt'
        #     }
        }
    )
    conn = engine.connect()
    return engine, conn 

def get_garmin_api():
    api = Garmin(os.environ.get("email"), os.environ.get("garmin-password"))
    api.login()
    return api

def collect_all(event, context):
    # Get cockroachdb
    engine, conn = get_cockroachdb_conn()    

    # Log to garmin API
    garmin_api = get_garmin_api()

    # Run collectors
    StatsCollector(garmin_api, conn).insert_new_data()
    StepsCollector(garmin_api, conn).insert_new_data()
    HeartRateCollector(garmin_api, conn).insert_new_data()
    StressCollector(garmin_api, conn).insert_new_data()
    HydrationCollector(garmin_api, conn).insert_new_data()
    SleepCollector(garmin_api, conn).insert_new_data()
    SleepLevelsCollector(garmin_api, conn).insert_new_data()
    WeightCollector(garmin_api, conn).insert_new_data()

    # close connection
    conn.close()
    engine.dispose()
