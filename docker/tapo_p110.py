"""P110 and P115 Example"""

import asyncio
import os
from datetime import datetime
from dotenv import load_dotenv
from tapo import ApiClient
from tapo.requests import EnergyDataInterval

load_dotenv()
async def tapo_auth():
    tapo_username = os.getenv("TAPO_USERNAME")
    tapo_password = os.getenv("TAPO_PASSWORD")
    ip_address = os.getenv("IP_ADDRESS")

    client = ApiClient(tapo_username, tapo_password)
    return await client.p110(ip_address)

async def device_info():
    device = await tapo_auth()
    return device.get_device_info()

async def device_on():
    device = await tapo_auth()
    return device.on()

async def device_off():
    device = await tapo_auth()
    return device.off()