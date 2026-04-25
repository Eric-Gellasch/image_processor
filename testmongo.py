from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

uri = "mongodb+srv://gellasch_db_user:Nurse0925@cluster0.k4ahrxd.mongodb.net/?appName=Cluster0"

client = MongoClient(uri, server_api=ServerApi("1"))

try:
    client.admin.command("ping")
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)
finally:
    client.close()