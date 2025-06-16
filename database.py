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
          
     async def get_payout_summary(self, period: str) -> List[Dict[str, Any]]:
          now = datetime.now()
          date_filter = None
          
          if period == 'week':
               date_filter = now - timedelta(days=7)
          elif period == 'month':
               date_filter = now - timedelta(days=30)
               
          if self.use_mongodb:
               match_stage = {}
               if date_filter:
                    match_stage = {'submitted_at': {'$gte'}: date_filter}
                    
               pipeline = [
                    {'$match': match_stage},
                    {'$group': {
                         "_id": '$discord_id',
                         'total_views': {'$sum': '$views'},
                         'total_earnigns': {'$sum': '$earnings'}
                    }}
               ]
               return list(self.clips.aggregate(pipeline))
          else:
               results = {}
               
               for clip in self.clips_data:
                    if date_filter and clip['submitted_at'] < date_filter:
                         continue
                    
                    user_id = clip['discord_id']
                    if user_id not in results:
                         results[user_id] = {
                              'id': user_id,
                              'total_views': 0,
                              'total_earnings': 0.0
                         }
                         
                    results[user_id]['total_views'] += clip['views']
                    results[user_id]['total_earnings'] += clip['earnings']
                    
               return list(results.values())
          
          
     async def export_to_csv(self, data: List[Dict[str, Any]]) -> str:
          output = StringIO()
          writer = csv.writer(output)
          writer.writerow(['Discord ID', 'Username', 'Total Views', 'Total Earnings'])
          
          for entry in data:
               writer.writerow([
                    entry['_id'],
                    'N/A', # Would need bot instance to resolve
                    entry['total_views'],
                    f"${entry['total_earnings']:.2f}"
               ])
               
          return output.getvalue()
     
     
     async def record_payout(self, user_id: int, admin_id: int):
          payout_data = {
               'user_id': user_id,
               'admin_id': admin_id,
               'paid_at': datetime.now()
          }
          
          if self.use_mongodb:
               self.payouts.insert_one(payout_data)
          else:
               self.payouts_data.append(payout_data)
               self.save_data()
               
     async def generate_analytics(self):
          #Simplified analytics implementation
          pass