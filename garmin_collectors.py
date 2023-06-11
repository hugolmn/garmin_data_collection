from abc import ABC, abstractclassmethod
import datetime
import pandas as pd

class GarminCollector(ABC):

    def __init__(self, garmin_api, conn, table):
        self.garmin_api = garmin_api
        self.conn = conn
        self.table = table

    @staticmethod
    def get_latest_data_point(conn, table):
        date_latest_point = conn.execute(
            f"""
            SELECT *
            FROM {table}
            ORDER BY date DESC
            LIMIT 1
            """
        ).fetchone()
        
        if date_latest_point:
            return date_latest_point[0]
        return []

    def create_list_missing_dates(self):
        date_latest_point = self.get_latest_data_point(self.conn, self.table)
        
        if (not date_latest_point):
            date_latest_point = datetime.date(2022, 8, 26) # First day of Garmin Venu 2 Plus watch
        elif type(date_latest_point) != datetime.date:
            date_latest_point = date_latest_point.date()
        
        if date_latest_point < datetime.date(2022, 8, 26):
            date_latest_point = datetime.date(2022, 8, 26)

        dates = pd.date_range(
            start=date_latest_point + datetime.timedelta(days=1), # day after latest point
            end=datetime.datetime.today().date() - datetime.timedelta(days=3), # 3 days before today
            freq='d'
        )
        return dates

    def insert_new_data(self):
        missing_dates = self.create_list_missing_dates()
        if not missing_dates.empty:
            df = self.collect_data(missing_dates)

            if 'date' in df.columns:
                try: 
                    df = df.drop_duplicates(subset=['date'], keep='first')
                    existing_dates = pd.read_sql(
                        f"""
                        SELECT date
                        FROM {self.table}
                        WHERE date IN ('{"', '".join(df.date.dt.strftime(date_format='%Y-%m-%d %H:%M'))}')
                        """,
                        con=self.conn
                    )
                    df = df[~df.date.isin(existing_dates.date)]
                except:
                    pass

            df.to_sql(
                self.table,
                self.conn,
                if_exists='append',
                index=False
            )
            print(f'{self.table}: {len(missing_dates)} new days added.')
        else:
            print(f'{self.table}: already up to date!')

    @abstractclassmethod
    def collect_data(self, missing_dates):
        pass


class StatsCollector(GarminCollector):

    def __init__(self, garmin_api, conn):
        super().__init__(garmin_api, conn, 'stats')

    def collect_data(self, dates):
        df = pd.DataFrame.from_dict([
            self.garmin_api.get_stats(date)
            for date in dates
        ])

        df = df[df.columns.intersection([
            # Date
            'calendarDate',
            # Calories
            'totalKilocalories',
            'activeKilocalories',
            'bmrKilocalories',
            # Steps
            'totalSteps',
            'totalDistanceMeters',
            # Activity level
            'highlyActiveSeconds',
            'activeSeconds',
            'sedentarySeconds',
            'sleepingSeconds',
            # Intense minutes
            'moderateIntensityMinutes',
            'vigorousIntensityMinutes',
            # Elevation
            'floorsAscendedInMeters',
            'floorsDescendedInMeters',
            # HR
            'minHeartRate',
            'maxHeartRate',
            'restingHeartRate',
            'lastSevenDaysAvgRestingHeartRate',
            # Stress
            'averageStressLevel',
            'maxStressLevel',
            'stressDuration',
            'restStressDuration',
            'activityStressDuration',
            'uncategorizedStressDuration',
            'totalStressDuration',
            'lowStressDuration',
            'mediumStressDuration',
            'highStressDuration',
            # Awake / Asleep
            'measurableAwakeDuration',
            'measurableAsleepDuration',
            # Body battery
            'bodyBatteryChargedValue',
            'bodyBatteryDrainedValue',
            'bodyBatteryHighestValue',
            'bodyBatteryLowestValue',
            # SPO2
            'averageSpo2',
            'lowestSpo2',
            # Breathing
            'avgWakingRespirationValue',
            'highestRespirationValue'
        ])]
        
        
        df = df.rename(columns={'calendarDate': 'date'})
        df = df.assign(date=pd.to_datetime(df['date']).dt.date)

        # https://stackoverflow.com/questions/1175208/elegant-python-function-to-convert-camelcase-to-snake-case
        df.columns = df.columns.str.replace(r'(?<!^)(?=[A-Z])', '_', regex=True).str.lower()
        
        df = pd.concat([
            df['date'],
            df.iloc[:, 1:].fillna(0).astype(int)
        ], axis=1)
        df = df.sort_values('date')
        return df


class StepsCollector(GarminCollector):

    def __init__(self, garmin_api, conn):
        super().__init__(garmin_api, conn, 'steps')

    def collect_data(self, dates):
        df = pd.concat([
            pd.DataFrame(self.garmin_api.get_steps_data(date.date()))
            for date in dates
        ])
        
        df = df[['startGMT', 'steps', 'primaryActivityLevel']]
        df.columns = ['date', 'steps', 'activity_level']

        df['date'] = pd.to_datetime(df.date, utc=True).dt.tz_convert('Europe/Paris').dt.tz_localize(None)

        df = df.assign(steps=df.steps.astype(int).fillna(0))
        df = df.sort_values(by='date')
        return df


class HeartRateCollector(GarminCollector):

    def __init__(self, garmin_api, conn):
        super().__init__(garmin_api, conn, 'heart_rate')

    def collect_data(self, dates):
        df = pd.concat([
            pd.DataFrame(
                self.garmin_api.get_heart_rates(date.date())['heartRateValues'],
                columns=['date', 'hr']
            )
            for date in dates
        ])
        
        df['date'] = pd.to_datetime(df['date'], unit='ms', utc=True).dt.tz_convert('Europe/Paris').dt.tz_localize(None)
        df['hr'] = df.hr.fillna(-1).astype(int)
        df = df.sort_values(by='date')
        return df


class StressCollector(GarminCollector):

    def __init__(self, garmin_api, conn):
        super().__init__(garmin_api, conn, 'stress')

    def collect_data(self, dates):
        df = pd.concat([
            pd.DataFrame(
                self.garmin_api.get_stress_data(date.date())['stressValuesArray'],
                columns=['date', 'stress']
            )
            for date in dates
        ])
        
        df['date'] = pd.to_datetime(df['date'], unit='ms', utc=True).dt.tz_convert('Europe/Paris').dt.tz_localize(None)
        df['stress'] = df.stress.astype(int)
        df = df.sort_values(by='date')
        return df


class HydrationCollector(GarminCollector):

    def __init__(self, garmin_api, conn):
        super().__init__(garmin_api, conn, 'hydration')

    def collect_data(self, dates):
        df = pd.DataFrame([
            self.garmin_api.get_hydration_data(date.date())
            for date in dates
        ])
        
        df = df[['calendarDate', 'valueInML', 'goalInML', 'sweatLossInML']]
        df.columns = ['date', 'value_in_ml', 'goal_in_ml', 'sweat_loss_in_ml']
        return df

class SleepCollector(GarminCollector):

    def __init__(self, garmin_api, conn):
        super().__init__(garmin_api, conn, 'sleep')

    def collect_data(self, dates):
        df = pd.concat([
            pd.json_normalize(self.garmin_api.get_sleep_data(date.date())['dailySleepDTO'])
            for date in dates
        ])
        
        column_mapping = {
            'calendarDate': 'date',
            'sleepStartTimestampGMT': 'sleep_start',
            'sleepEndTimestampGMT': 'sleep_end',
            'sleepTimeSeconds': 'sleep_time_seconds',
            'deepSleepSeconds': 'deep_sleep_seconds',
            'lightSleepSeconds': 'light_sleep_seconds',
            'remSleepSeconds': 'rem_sleep_seconds',
            'awakeSleepSeconds': 'awake_sleep_seconds',
            'averageSpO2Value': 'average_spo2',
            'lowestSpO2Value': 'lowest_spo2',
            'highestSpO2Value': 'highest_spo2',
            'averageSpO2HRSleep': 'average_spo2',
            'averageRespirationValue': 'average_hr_sleep',
            'lowestRespirationValue': 'lowest_respiration',
            'highestRespirationValue': 'highest_respiration',
            'awakeCount': 'awake_count',
            'avgSleepStress': 'avg_sleep_stress',
            'sleepScores.overall.value': 'sleep_score'
        }

        df = df[df.columns.intersection(column_mapping.keys())]

        df = df.rename(columns=column_mapping)
        df = df.assign(date=pd.to_datetime(df['date']).dt.date)
        df['sleep_start'] = pd.to_datetime(df['sleep_start'], unit='ms', utc=True).dt.tz_convert('Europe/Paris').dt.tz_localize(None)
        df['sleepEndTimestampGMT'] = pd.to_datetime(df['sleepEndTimestampGMT'], unit='ms', utc=True).dt.tz_convert('Europe/Paris').dt.tz_localize(None)

        return df

class SleepLevelsCollector(GarminCollector):

    def __init__(self, garmin_api, conn):
        super().__init__(garmin_api, conn, 'sleep_levels')

    def collect_data(self, dates):
        df = pd.concat([
            pd.DataFrame(self.garmin_api.get_sleep_data(date)['sleepLevels']).assign(date=date)
            for date in dates
        ])
        
        df['date'] = pd.to_datetime(df.date)
        df['level_start'] = pd.to_datetime(df['startGMT'], utc=True).dt.tz_convert('Europe/Paris').dt.tz_localize(None)
        df['level_end'] = pd.to_datetime(df['endGMT'], utc=True).dt.tz_convert('Europe/Paris').dt.tz_localize(None)
        df = df.assign(
            date=df.level_end.dt.date,
            activity_level=df.activityLevel.astype(int)
        )
        df = df[[
            'date',
            'level_start',
            'level_end',
            'activity_level',
        ]]

        return df

class WeightCollector(GarminCollector):

    def __init__(self, garmin_api, conn):
        super().__init__(garmin_api, conn, 'weight')

    def collect_data(self, dates):
        record_list = []
        for date in dates:
            if weight_data := self.garmin_api.get_body_composition(date.date())['dateWeightList']:
                record_list.append(*weight_data)

        if record_list:
            df = pd.DataFrame(record_list)
            df = df[['calendarDate', 'weight']]
            df = df.assign(weight=df.weight/1000)
            df = df.rename(columns={'calendarDate': 'date'})
            return df
        else:
            return pd.DataFrame()
