import json
import pymysql
import os
import random
from slack import send_slack_message
from menu_crawler import VetRestaurantCrawler, GraduateDormRestaurantCrawler, SnucoRestaurantCrawler

def crawl(event, context):
    try:
        siksha_db = pymysql.connect(
            user=os.environ.get('DB_USER', 'root'),
            passwd=os.environ.get('DB_PASSWORD', 'waffle'),
            host=os.environ.get('DB_HOST', '127.0.0.1'),
            db=os.environ.get('DB_NAME', 'siksha'),
            charset='utf8'
        )
        cursor = siksha_db.cursor(pymysql.cursors.DictCursor)
        # TRANSACTION START
        get_restaurants_query = """
            SELECT *
            FROM restaurant
        """
        cursor.execute(get_restaurants_query)
        restaurants = cursor.fetchall()
        print('log using stdout')
        print(f'get restaurants result: {repr(restaurants)}')
        insert_restaurants_query = """
            INSERT INTO restaurant(code, name_kr, name_en, addr, lat, lng)
            VALUES (%(code)s, %(name_kr)s, %(name_en)s, %(addr)s, %(lat)s, %(lng)s);
        """
        new_restaurants = [
            dict(
                code=f"test{random.random()}",
                name_kr="한글명",
                name_en="영어명",
                addr="한글주소",
                lat=0,
                lng=0
            ) for i in range(10)
        ]
        cursor.executemany(insert_restaurants_query, new_restaurants)
        # TRANSACTION END
        siksha_db.commit()
        send_slack_message("crawling has been successfully done")
        return "crawling has been successfully done"
    except:
        siksha_db.rollback()
        send_slack_message("crawling has been failed")
        return "crawling has been failed"
