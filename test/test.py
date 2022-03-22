import asyncio
import aiohttp
import random
import json

def main() :

    loop = asyncio.get_event_loop()
    loop.run_until_complete(performHttpRequest())
    loop.close()

async def performHttpRequest() :

    async with aiohttp.ClientSession() as session :

        tasks = getTasks(session)

        responses = await asyncio.gather(*tasks)

        for response in responses :

            try :

                print(await response.json())

            except (json.decoder.JSONDecodeError, aiohttp.client_exceptions.ContentTypeError) :

                print(await response.text())

def getTasks(session) :

    tasks = []

    for i in range(50) :

        randomTimeout = random.randint(300,80000)

        tasks.append(session.get( "http://localhost:5000/api/smart/" + str(randomTimeout), ssl=False) )

    return tasks

if __name__ == "__main__": 

    main()