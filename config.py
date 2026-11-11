
import mysql.connector

def connect():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="Jashnavi 09%",
        database="stocksense_db"
    )
