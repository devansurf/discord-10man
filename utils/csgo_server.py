import discord
import logging
import valve.rcon
import requests
import json

from discord.ext.commands import Context
from typing import Dict, List
from logging.config import fileConfig

class CSGOServer:
    #called from bot.py
    def __init__(self, identifier: int, server_address: str, server_port: int, server_password: str,
                 RCON_password: str, server_id: str, DH_email: str, DH_password: str, match_settings: dict):
        fileConfig('logging.conf')
        self.logger = logging.getLogger(f'10man.{__name__}')

        self.id: int = identifier
        self.server_address: str = server_address
        self.server_port: int = server_port
        self.server_id: str = server_id
        self.server_password: str = server_password
        self.RCON_password: str = RCON_password
        self.available: bool = True
        self.gotv: int = None
        self.DH_email: str = DH_email
        self.DH_password: str = DH_password
        self.match_settings: dict = match_settings
        self.logger.debug(f'Created CSGO Server {self.id}')

        self.ctx: Context = None
        self.channels: List[discord.VoiceChannel] = None
        self.players: List[discord.Member] = None
        self.score_message: discord.Message = None
        self.team_names: List[str] = None
        self.team_scores: List[int] = [0, 0]

    def get_context(self, ctx: Context, channels: List[discord.VoiceChannel], players: List[discord.Member],
                    score_message: discord.Message):
        self.ctx = ctx
        self.channels = channels
        self.players = players
        self.score_message = score_message
        self.logger.debug(f'ServerID:{self.id} got context')

    def get_auth_header(self):
        return (self.DH_email, self.DH_password)
    
    def get_account(self): 
        r = requests.get('https://dathost.net/api/0.1/account', auth=self.get_auth_header())
        self.logger.debug(f'Request to get account returned code {r.status_code}')

    def format_players(self, player_dict):  
        formatted = ','.join(list(player_dict.keys()))
        return formatted.replace('_0', '_1')

    def start_match(self, match_config: Dict):
        #format match_config for datahost
        print(list(match_config['team1']['players'].keys()))
        self.match_settings['game_server_id'] = self.server_id
        self.match_settings['map'] = match_config['maplist'][0]

        self.match_settings['team1_name'] = match_config['team1']['name']
        self.match_settings['team1_flag'] = match_config['team1']['flag']
        self.match_settings['team1_steam_ids'] = self.format_players(match_config['team1']['players'])

        self.match_settings['team2_name'] = match_config['team2']['name']
        self.match_settings['team2_flag'] = match_config['team2']['flag']
        self.match_settings['team2_steam_ids'] = self.format_players(match_config['team2']['players'])

        self.match_settings['spectators_steam_ids'] = self.format_players(match_config['spectators']['players'])

        response = requests.post('https://dathost.net/api/0.1/matches',data=self.match_settings,auth=self.get_auth_header())
        self.logger.debug(f'POST request to start match returned code {response.status_code}')

    def set_map(self, csgo_map: str):
        r = requests.put(f'https://dathost.net/api/0.1/game-servers/{self.server_id}', data={'csgo_settings.mapgroup_start_map':csgo_map},
            auth=self.get_auth_header())
        self.logger.debug(f'Request to put map returned code {r.status_code}')
        
    def set_team_names(self, team_names: List[str]):
        self.team_names = team_names
        self.logger.debug(f'ServerID:{self.id} got team_names: {team_names}')

    def update_team_scores(self, team_scores: List[int]):
        self.team_scores = team_scores
        self.logger.debug(f'ServerID:{self.id} got team_names: {team_scores}')

    def make_available(self):
        self.available: bool = True
        self.ctx: Context = None
        self.channels: List[discord.VoiceChannel] = None
        self.players: List[discord.Member] = None
        self.score_message: discord.Message = None
        self.team_names: List[str] = None
        self.team_scores: List[int] = [0, 0]
        self.logger.info(f'ServerID:{self.id} is available')

    def get_gotv(self) -> int:
        if self.gotv is None:
            tv_port: str = valve.rcon.execute((self.server_address, self.server_port), self.RCON_password, 'tv_port')
            self.logger.debug(tv_port)
            try:
                self.gotv = tv_port[CSGOServer.findNthOccur(tv_port, '"', 3) + 1:CSGOServer.findNthOccur(tv_port, '"', 4)]
            except ValueError or valve.rcon.RCONMessageError:
                self.gotv = None

        self.logger.info(f'ServerID={self.id} GoTV={self.gotv}')
        return self.gotv

    @staticmethod
    def findNthOccur(string, ch, N):
        occur = 0

        for i in range(len(string)):
            if string[i] == ch:
                occur += 1

            if occur == N:
                return i

        return -1
