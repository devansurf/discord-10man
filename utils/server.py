import discord
import logging
import os
import pprint
import socket
import traceback
import uuid
import valve.rcon

from discord.ext import tasks
from aiohttp import web
from json import JSONDecodeError
from logging.config import fileConfig
from typing import List, Union
from utils.csgo_server import CSGOServer


class WebServer:
    def __init__(self, bot):
        from bot import Discord_10man

        fileConfig('logging.conf')
        self.logger = logging.getLogger(f'10man.{__name__}')

        self.bot: Discord_10man = bot
        self.IP: str = socket.gethostbyname(socket.gethostname())
        self.port: int = self.bot.bot_port
        self.site: web.TCPSite = None
        self.csgo_servers: List[CSGOServer] = []
        self.map_veto_image_path = self.create_new_veto_filepath()

    def create_new_veto_filepath(self):
        path = f'/map-veto/{str(uuid.uuid1())}'
        return path

    # @tasks.loop(seconds = 10.0)
    # async def fetch_servers(self):
    #      #gather server stats
    #     for server in self.csgo_servers:
    #         match_info = server.get_match_info()
    #         if match_info != None:
    #             #checks
    #             if match_info['finished']:
    #                 score_embed: discord.Embed = server.score_message.embeds[0]
    #                 score_embed.set_footer(text='🟥 Ended')
    #                 await server.score_message.edit(embed=score_embed)
    #                 if self.bot.cogs['CSGO'].pug.enabled:
    #                     for player in server.players:
    #                         try:
    #                             await player.move_to(channel=server.channels[0], reason=f'Game Over')
    #                         except discord.HTTPException:
    #                             traceback.print_exc()
    #                             print(f'Unable to move {player}')
    #                 await server.channels[1].delete(reason='Game Over')
    #                 await server.channels[2].delete(reason='Game Over')
    #                 server.make_available()
    #                 self.csgo_servers.remove(server)

    #     self.logger.info('Completed fetching info from all csgo servers')

    async def _handler(self, request: web.Request) -> Union[web.Response, web.FileResponse]:
        """
        Super simple HTTP handler.
        Parameters
        ----------
        request : web.Request
            AIOHTTP request object.
        """
        #https://docs.aiohttp.org/en/stable/web_reference.html
        
        if request.method == 'GET':
            if request.path == '/match':
                self.logger.debug(f'{request.remote} accessed {self.IP}:{self.port}/match')
                return web.FileResponse('./match_config.json')
            elif request.path == '/map-veto':
                self.logger.debug(f'{request.remote} accessed {self.IP}:{self.port}/map-veto')
                self.map_veto_image_path = self.create_new_veto_filepath()
                response = {'path': self.map_veto_image_path}
                return web.json_response(response)
            elif request.path == self.map_veto_image_path:
                self.logger.debug(f'{request.remote} accessed {self.IP}:{self.port}/{self.map_veto_image_path}')
                return web.FileResponse('./result.png')
            else:
                self.logger.debug(f'{request.remote} accessed {self.IP}:{self.port}{request.path}')
                if os.path.isfile(f'./{request.path}.json'):
                    self.logger.info('File Found')
                    return web.FileResponse(f'./{request.path}.json')
                else:
                    self.logger.error('Invalid Request, File not Found')
                    return WebServer._http_error_handler('file not found')

        # or "Authorization"
        elif request.method == 'POST':
            try:
                datahost_event = await request.json()
            except JSONDecodeError:
                self.logger.warning(f'{request.remote} sent a invalid json POST ')
                return WebServer._http_error_handler('json-body')

            # TODO: Create Checks for the JSON

            server = None
            for csgo_server in self.csgo_servers:
                #IMPORTANT ONLY ALLOW POST FROM TRUSTED SOURCE. ID should match servers match_id
                print(request.remote)
                if datahost_event['id'] == csgo_server.match_id:
                    server = csgo_server
                    break
            
            print(request.remote)
            print(self.bot.bot_IP)
            if server is not None and request.remote == self.bot.bot_IP:
                self.logger.debug(f'ServerID={server.id} ({request.remote})=\n {pprint.pformat(datahost_event)}')
                print(request.path)
                if request.path == '/match_end':

                    await server.score_message.edit(content='Game Over')

                    score_embed: discord.Embed = server.score_message.embeds[0]
                    score_embed.set_footer(text='🟥 Ended')
                    await server.score_message.edit(embed=score_embed)

                    if os.path.exists(f'./{server.json_id}.json'):
                        os.remove(f'./{server.json_id}.json')
                        self.logger.debug(f'Deleted {server.json_id}.json')
                    else:
                        self.logger.error(f'Could not delete {server.json_id}.json, file does not exist')

                    if self.bot.cogs['CSGO'].pug.enabled:
                        for player in server.players:
                            try:
                                await player.move_to(channel=server.channels[0], reason=f'Game Over')
                            except discord.HTTPException:
                                traceback.print_exc()
                                print(f'Unable to move {player}')
                    await server.channels[1].delete(reason='Game Over')
                    await server.channels[2].delete(reason='Game Over')
                    server.make_available()
                    self.csgo_servers.remove(server)

                elif request.path == '/round_end':
                    server.update_team_scores(
                        [datahost_event['team1_stats']['score'], datahost_event['team2_stats']['score']])
                    score_embed = discord.Embed()
                    score_embed.add_field(name=f'{datahost_event["params"]["team1_score"]}',
                                          value=f'{server.team_names[0]}', inline=True)
                    score_embed.add_field(name=f'{datahost_event["params"]["team2_score"]}',
                                          value=f'{server.team_names[1]}', inline=True)
                    gotv = server.get_gotv()
                    if gotv is None:
                        score_embed.add_field(name='GOTV',
                                              value='Not Configured',
                                              inline=False)
                    else:
                        score_embed.add_field(name='GOTV',
                                              value=f'connect {server.server_address}:{gotv}',
                                              inline=False)
                    score_embed.set_footer(text="🟢 Live")
                    await server.score_message.edit(embed=score_embed)

                if datahost_event['event'] == 'series_end' or datahost_event['event'] == 'series_cancel' or datahost_event['event'] == 'map_end':
                    if datahost_event['event'] == 'series_end':
                        await server.score_message.edit(content='Game Over')
                    elif datahost_event['event'] == 'series_cancel':
                        self.logger.info(f'ServerID={server.id} | Admin Cancelled Match')
                        await server.score_message.edit(content='Game Cancelled by Admin')
                        # Temporary fix, Get5 breaks on a series cancel unless map changes
                        valve.rcon.execute((server.server_address, server.server_port), server.RCON_password,
                                           'sm_map de_mirage')

                    score_embed: discord.Embed = server.score_message.embeds[0]
                    score_embed.set_footer(text='🟥 Ended')
                    await server.score_message.edit(embed=score_embed)

                    if os.path.exists(f'./{datahost_event["matchid"]}.json'):
                        os.remove(f'./{datahost_event["matchid"]}.json')
                        self.logger.debug(f'Deleted {datahost_event["matchid"]}.json')
                    else:
                        self.logger.error(f'Could not delete {datahost_event["matchid"]}.json, file does not exist')

                    if self.bot.cogs['CSGO'].pug.enabled:
                        for player in server.players:
                            try:
                                await player.move_to(channel=server.channels[0], reason=f'Game Over')
                            except discord.HTTPException:
                                traceback.print_exc()
                                print(f'Unable to move {player}')
                    await server.channels[1].delete(reason='Game Over')
                    await server.channels[2].delete(reason='Game Over')
                    server.make_available()
                    self.csgo_servers.remove(server)
        else:
            # Used to decline any requests what doesn't match what our
            # API expects.
            self.logger.warning(f'{request.remote} sent an invalid request.')
            return WebServer._http_error_handler("request-type")

        return WebServer._http_error_handler()

    async def http_start(self) -> None:
        """
        Used to start the webserver inside the same context as the bot.
        """
        server = web.Server(self._handler)
        runner = web.ServerRunner(server)
        await runner.setup()
        self.site = web.TCPSite(runner, self.IP, self.port)
        await self.site.start()
        self.logger.info(f'Webserver Started on {self.IP}:{self.port}')

    async def http_stop(self) -> None:
        """
        Used to stop the webserver inside the same context as the bot.
        """
        self.logger.warning(f'Webserver Stopping on {self.IP}:{self.port}')
        await self.site.stop()

    def add_server(self, csgo_server: CSGOServer):
        print("added csgo server")
        self.csgo_servers.append(csgo_server)

    @staticmethod
    def _http_error_handler(error: str = 'Undefined Error') -> web.Response:
        """
        Used to handle HTTP error response.
        Parameters
        ----------
        error : bool, optional
            Bool or string to be used, by default False
        Returns
        -------
        web.Response
            AIOHTTP web server response.
        """

        return web.json_response(
            {"error": error},
            status=400 if error else 200
        )
