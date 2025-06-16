import os, json, csv, pymongo
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from io import StringIO
from pymongo import MongoClient
from config import Config

class Database:
     def __init__(self):
          self.config = Config
          self.connect()
          
     def conenct(self):
          if os.getenv('MONGODB_URL'):
               try:
                    self.client = MongoClient(os.getenv('MONGODB_URL'))
                    self.db = self.client['clipper_bot']
                    self.users = self.db['users']
                    self.clips = self.db['clips']
                    self.payouts = self.db['payouts']
                    self.analytics = self.db['analytics']
                    self.use_mongodb = True
               except Exception as e:
                    print(f"MongoDB connection failed: {e}")
                    self.use_mongodb = False
                    
          else:
               self.use_mongodb = False
               
          if not self.use_mongodb:
               self.data_file = 'data.json'
               self.laod_data()
               
     def load_data(self):
          try:
               with open(self.data_file) as file:
                    data = json.load(file)
                    self.users_data = data.get('users', {})
                    self.clips_data = data.get('clips', [])
                    self.payouts_data = data.get('payouts', [])
                    self.analytics_data = data.get('analytics', [])
          except FileExistsError:
               self.users_data = {}
               self.clips_data = {}
               self.payouts_data = {}
               self.analytics_data = {}
               
     def dave_data(self):
          if not self.use_mongodb:
               data = {
                    'users': self.users_data,
                    'clips': self.clips_data,
                    'payouts': self.payouts_data,
                    'analytics': self.analytics_data
               }
               with open(self.data_file, 'w') as file:
                    json.dump(data, file, default=str)
                    
                    
     async def store_verified_user(self, user_id: int, platform: str, username: str):
          user_data = {
            'discord_id': user_id,
            'platform': platform,
            'username': username,
            'verified_at': datetime.now(),
            'total_views': 0,
            'total_earnings': 0.0
          }
          
          if self.use_mongodb:
               self.users.update_one(
                    {'discord_id': user_id},
                    {'$set': user_data},
                    upsert=True
               )
               
          else:
               self.users_data[str(user_id)] = user_data
               self.save_data()
               
     async def store_clip(self, clip_data: dict):
          if self.use_mongodb:
               self.clips.insert_one(clip_data)
               
               # Update user stats
               self.users.update_one(
                    {'discord_id': clip_data['discord_id']},
                    {
                         '$inc': {
                              'total_views': clip_data['views'],
                              'total_earnings': clip_data['earnings']
                         }
                    }
               )
          else:
               self.clips_data.append(clip_data)
               
               
               # update user stats
               user_id = str(clip_data['discord_id'])
               if user_id in self.users_data:
                    self.users_data[user_id]['total_views'] += clip_data['views']
                    self.users_data[user_id]['total_earnings'] += clip_data['earnings']
                    
                    self.save_data()
                    
     async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
          if self.use_mongodb:
               return self.users.find_one({'discord_id': user_id})
          else:
               return self.users_data.get(str(user_id))
          
               