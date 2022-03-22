import aiohttp
import asyncio
import json
import logging
import psutil
import time
from datetime import datetime
from flask import Flask
from flask import jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from multiprocessing import Process, Queue
from uuid import uuid4

app = Flask("HTTP Assesment Server")
limiter = Limiter(app, key_func=get_remote_address)
# maximum of requests per minute
requestsPerMinuteLimit = 50000000
# the maximum length of running program in milliseconds
maxTimeout = 60000
logging.basicConfig(filename='logs/logs.log', level=logging.INFO,
                    format='%(asctime)s : %(levelname)s : %(name)s : %(message)s')
logWerkzeug = logging.getLogger('werkzeug')
logWerkzeug.disabled = True

app.config['JSON_SORT_KEYS'] = False


@app.route("/api/smart/")
@limiter.limit(f'''{requestsPerMinuteLimit}/minute''')
def checkIfParameterProvided():
    eventId = datetime.now().strftime('%Y%m-%d%H-%M%S-') + str(uuid4())

    app.logger.info(f'''{eventId} : Please, provide the timeout parameter specifying time in milliseconds.''')

    return "Please, provide the timeout parameter specifying time in milliseconds."


@app.route("/api/smart/<timeout>/")
@limiter.limit(f'''{requestsPerMinuteLimit}/minute''')
def runApi(timeout):
    eventId = datetime.now().strftime('%Y%m-%d%H-%M%S-') + str(uuid4())

    if timeout.isnumeric() == False:

        app.logger.info(
            f'''{eventId} : Invalid timeout parameter type. Please, provide positive integer value. The timeout parameter specifies time in milliseconds.''')

        return "Invalid timeout parameter type. Please, provide positive integer value. The timeout parameter specifies time in milliseconds."

    else:

        # if the provided timeout parameter is lower than maxTimeout value, then use the timeout parameter
        # this will handels the timeout for all three processes firing HTTP requests
        # convert provided timeout to seconds
        if int(timeout) > maxTimeout:

            timeout = maxTimeout

            app.logger.info(
                f'''{eventId} : Provided timeout is higher than the maximum timeout limit {maxTimeout} milliseconds.''')

        else:

            timeout = int(timeout)

        app.logger.info(f'''{eventId} : Timeout parameter set to {timeout} milliseconds.''')

        # queue to receive the first successful response
        queueHttpRequestResult = Queue()

        processPerformHttpRequest = Process(target=performHttpRequests, args=(queueHttpRequestResult, eventId,))
        processPerformHttpRequest.start()

        processPerformHttpRequestPid = processPerformHttpRequest.pid
        parentProcessPerformHttpRequestToKillChild = psutil.Process(processPerformHttpRequestPid)

        app.logger.info(f'''{eventId} : Id of process performing HTTP request {processPerformHttpRequestPid}.''')

        # terminate the process in case it takes longer to receive the first successful response than the timeout value
        # testing server performs some work (taking roughly 100-600 ms) - > variable maxTimeout
        processPerformHttpRequest.join(timeout=timeout / 1000)

        try:

            # in case it times out earlier then it takes to receive the first successful response, some subprocesses could be running
            childProcessPerformHttpRequestToKill = parentProcessPerformHttpRequestToKillChild.children(recursive=True)

            for child in childProcessPerformHttpRequestToKill:
                child.kill()

                app.logger.info(
                    f'''{eventId} : The child process {child.pid} of the parent process {processPerformHttpRequestPid} has been terminated.''')

        except psutil.NoSuchProcess:

            app.logger.info(
                f'''{eventId} : The parent process {processPerformHttpRequestPid} tried to kill the process that no longer exists.''')

        processPerformHttpRequest.terminate()
        app.logger.info(
            f'''{eventId} : The parent process {processPerformHttpRequestPid} performing HTTP request has been terminated.''')

        # in case the proces timed out, queue is empty
        if queueHttpRequestResult.empty() == True:

            return "Error: The HTTP Assesment Server request has timed out."

        else:

            firstSuccessfulResponse = queueHttpRequestResult.get()

            # create dictionary
            response = {

                "time": int(firstSuccessfulResponse.split(", ")[1]),
                "requestAttemptNo.": int(firstSuccessfulResponse.split(", ")[0])
            }

            app.logger.info(f'''{eventId} : Response returned.''')

            return jsonify(response)

    # run 2 processes 
    # 1st to allow 3 get requests in parallel
    # 2nd to read from task


def performHttpRequests(queueHttpRequestResult, eventId):
    # global variable for processPerformThreeHttpRequests & processGetFirstSuccessfulResponse (fifo queue)
    queueThreeHttpRequestsResults = Queue()

    processPerformThreeHttpRequests = Process(target=performThreeHttpRequests,
                                              args=(queueThreeHttpRequestsResults, eventId,))
    processPerformThreeHttpRequests.start()

    processPerformThreeHttpRequestsPid = processPerformThreeHttpRequests.pid
    parentProcessPerformThreeHttpRequestsToKillChild = psutil.Process(processPerformThreeHttpRequestsPid)

    app.logger.info(
        f'''{eventId} : Id of parent process performing three HTTP requests {processPerformThreeHttpRequestsPid}.''')

    processGetFirstSuccessfulResponse = Process(target=getFirstSuccessfulResponse,
                                                args=(queueThreeHttpRequestsResults, queueHttpRequestResult, eventId,))
    processGetFirstSuccessfulResponse.start()
    processGetFirstSuccessfulResponsePid = processGetFirstSuccessfulResponse.pid

    app.logger.info(
        f'''{eventId} : Id of process waiting for the first successful response {processGetFirstSuccessfulResponsePid}.''')

    # wait for processGetFirstSuccessfulResponse to finish
    processGetFirstSuccessfulResponse.join()

    # the first successful response received, terminate processPerformThreeHttpRequests's children
    # terminate() kills only the parent process, deamon=True (daemonic processes are not allowed to have children)
    # get active child processes and kill()
    try:

        childProcessesPerformThreeHttpRequestsToKill = parentProcessPerformThreeHttpRequestsToKillChild.children(
            recursive=True)

        # in case the process processGetFirstSuccessfulResponse terminates earlier than the processPerformThreeHttpRequests's children
        for child in childProcessesPerformThreeHttpRequestsToKill:
            child.kill()

            app.logger.info(
                f'''{eventId} : The child process {child.pid} of the parent process {processPerformThreeHttpRequestsPid} performing HTTP request has been terminated.''')

        # in case the processPerformThreeHttpRequests children terminates earlier than the process getFirstSuccessfulResponse
    except psutil.NoSuchProcess:

        app.logger.info(
            f'''{eventId} : The parent process {processPerformThreeHttpRequestsPid} children does not exist.''')

        # in case it terminates earlier than processGetFirstSuccessfulResponse or processPerformHttpRequest terminates it (timeout)
    if processPerformThreeHttpRequests.is_alive():
        processPerformThreeHttpRequests.terminate()
        app.logger.info(
            f'''{eventId} : The parent process {processPerformThreeHttpRequestsPid} performing three HTTP requests has been terminated.''')

        # in case the processPerformHttpRequest terminates it (timeout)
    if processPerformThreeHttpRequests.is_alive():
        processGetFirstSuccessfulResponse.terminate()
        app.logger.info(
            f'''{eventId} : The process {processGetFirstSuccessfulResponsePid} waiting for the first successful response has been terminated.''')


def performThreeHttpRequests(queueThreeHttpRequestsResults, eventId):
    # run process 1 and sleep for 300 milliseconds
    # await to put response in queueThreeHttpRequestsResults
    processFirstRequest = Process(target=getResponseEventLoop, args=(queueThreeHttpRequestsResults, 1, eventId,))
    processFirstRequest.start()
    processFirstRequestPid = processFirstRequest.pid

    app.logger.info(f'''{eventId} : The first request has been fired. Pid {processFirstRequestPid}.''')

    # If there is no successful response within 300 milliseconds, it fires another 2 requests.
    time.sleep(0.003)

    processSecondRequest = Process(target=getResponseEventLoop, args=(queueThreeHttpRequestsResults, 2, eventId,))
    processSecondRequest.start()
    processSecondRequestPid = processSecondRequest.pid

    app.logger.info(f'''{eventId} : The second request has been fired. Pid {processSecondRequestPid}.''')

    processThirdRequest = Process(target=getResponseEventLoop, args=(queueThreeHttpRequestsResults, 3, eventId,))
    processThirdRequest.start()
    processThirdRequestPid = processThirdRequest.pid

    app.logger.info(f'''{eventId} : The third request has been fired. Pid {processThirdRequestPid}.''')

    # to avoid error get symbols was never awaited
    # event loop checking to see if there are async processes done


def getResponseEventLoop(queueThreeHttpRequestsResults, requestNo, eventId):
    loop = asyncio.get_event_loop()
    loop.run_until_complete(getResponse(queueThreeHttpRequestsResults, requestNo, eventId))
    loop.close()


async def getResponse(queueThreeHttpRequestsResults, requestNo, eventId):
    async with aiohttp.ClientSession() as session:

        # It performs some work (taking roughly 100-600 ms)
        #response = await session.get('https://exponea-engineering-assignment.appspot.com/api/work', ssl=False)
        response = {'time': 160}

        try:

            # a response which returns HTTP status code 200 and has a valid payload
            # response example {“time”: 160}
            #responseResult = await response.json()
            responseResult = response

            if "time" in responseResult and type(responseResult["time"]) == int:

                app.logger.info(f'''{eventId} : Request no. {requestNo} returned valid response.''')
                queueThreeHttpRequestsResults.put(str(requestNo) + ", " + str(responseResult["time"]))

            else:

                app.logger.info(f'''{eventId} : Request no. {requestNo} didn't return valid response.''')

            # handle error if deserialization fails
            # if the reponse is 'Too many requests' or 'Internal server error'
        except (json.decoder.JSONDecodeError, aiofhttp.client_exceptions.ContentTypeError):

            app.logger.info(f'''{eventId} : Request no. {requestNo} didn't return valid response.''')


def getFirstSuccessfulResponse(queueThreeHttpRequestsResults, queueHttpRequestResult, eventId):
    while queueThreeHttpRequestsResults.empty():
        continue

        # fifo
    firstSuccessfulResponse = queueThreeHttpRequestsResults.get()
    app.logger.info(f'''{eventId} : The first successful response has been received.''')
    queueHttpRequestResult.put(firstSuccessfulResponse)


if __name__ == "__main__":
    # threaded=True to handle concurrent requests
    app.run(threaded=True, debug=False)
