import os, sys, re, time
import datetime
import glob
import shutil
import random

import simplejson as json
import subprocess
import numpy as np
import urllib, requests
import httplib2
from urllib.parse import urlencode
from fractions import Fraction
import math

import googleapiclient.discovery
from pytube import YouTube
from google.cloud import texttospeech

# Libraries for Youtube video upload
from apiclient.discovery import build
from apiclient.errors import HttpError
from apiclient.http import MediaFileUpload
from oauth2client.client import flow_from_clientsecrets
from oauth2client.file import Storage
from oauth2client.tools import argparser, run_flow
from oauth2client import client

import apivideo
from apivideo.apis import VideosApi
from apivideo.exceptions import ApiAuthException

import spacy
from collections import Counter
from string import punctuation


os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getcwd() + os.path.sep + "storymerge-775cc31bde1f.json"
#DEVELOPER_KEY = 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
DEVELOPER_KEY = 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'

"""
Dependencies: ffmpeg, python3, GOOGLE_APPLICATION_CREDENTIALS, pytube, googleapiclient, api.video
Check requirements.txt for other python modules used.
"""

# TODO: 
"""
1. Organize real-input.txt to the discussed text script rules. [Done]
2. Sync text script overlay with voice over track. [Done]
3. Modify function 'getaudiofromtext' to retrieve voice-over track for a given text from Sergey's ReST API. [Done]
4. Investigate and fix the issue of video stream freezing. (priority) [Improved after adding '-strict', '-preset', and '-pix_fmt'.][Done]
"""


def v_concatmp4streams(mp4file_1, mp4file_2, mp4outfile):
    cmd = "ffmpeg -y -i %s -i %s -filter_complex \"[0:v] [1:v] concat=n=2:v=1 [v]\" -map \"[v]\" -pix_fmt yuv420p %s"%(mp4file_1, mp4file_2, mp4outfile)
    subprocess.call(cmd, shell=True)
    return mp4outfile


def va_concatmp4streams(mp4file_1, mp4file_2, mp4outfile):
    tmpfile1 = mp4file_1.split(".")[0] + "_concat.mp4"
    fi = open(mp4file_1, "rb")
    file1content = fi.read()
    fi.close()
    fo = open(tmpfile1, "wb")
    fo.write(file1content)
    fo.close()
    #cmd = "ffmpeg -y -i %s -i %s -filter_complex \"[0:v] [0:a] [1:v] [1:a] concat=n=2:v=1:a=1 [v] [a]\" -map \"[v]\" -map \"[a]\" -strict -2 -preset slow -pix_fmt yuv420p %s"%(tmpfile1, mp4file_2, mp4outfile)setdar=16:ceil(ih/2)*2,
    cmd = "ffmpeg -y -i %s -i %s -filter_complex \"[0]scale=ceil(iw/2)*2:ceil(ih/2)*2[a];[1]scale=ceil(iw/2)*2:ceil(ih/2)*2[b]; [a][0:a][b][1:a]concat=n=2:v=1:a=1 [v] [a]\" -map \"[v]\" -map \"[a]\" -strict -2 -preset slow -pix_fmt yuv420p %s"%(tmpfile1, mp4file_2, mp4outfile)
    errcode = subprocess.call(cmd, shell=True)
    if errcode > 0: # Some error occurred during execution of the command
        return None
    # If mp4outfile exists and it size is > 0, then remove tmpfile1. Else, rename mp4file_1 to mp4outfile and remove tmpfile1.
    if os.path.exists(mp4outfile) and os.path.getsize(mp4outfile) > 0:
        os.unlink(tmpfile1)
    else:
        try:
            os.rename(mp4file_1, mp4outfile)
            os.unlink(tmpfile1)
        except:
            print("Error: %s"%sys.exc_info()[1].__str__())
            print("You will have temporary files in the system after this operation. Please remove them manually.")
    return mp4outfile


"""
Create a storyfile out of a free-form text file:
Sentences that end with a question mark or colon are considered to
be section headers. The remaining text till the next section header
is the content of this section.
The first line of the file is the file header.
The function creates a story file that adheres to the rules specified
in the function 'readandsegmenttext'.
"""
def createstoryfile(textfile):
    if not os.path.exists(textfile):
        return None
    ft = open(textfile, "r")
    textcontent = ft.read()
    ft.close()
    headerpattern = re.compile("[\?\:]{1}\s*$")
    emptypattern = re.compile("^\s*$")
    parenthesispattern = re.compile("^([^\(]+)(\([^\)]+\))(.*)$", re.DOTALL)
    startperiodpattern = re.compile("^\s*\.")
    alllines = textcontent.split("\n")
    lctr = 0
    sectionctr = 1
    firstline = True
    sectionlines = []
    headers = []
    for line in alllines:
        line = line.replace("\n", "").replace("\r", "")
        # If there is a parenthesized text in any line, put a comma before it and a comma or period after it.
        if firstline and not re.search(emptypattern, line):
            pps = re.search(parenthesispattern, line)
            if pps:
                if re.search(startperiodpattern, pps.groups()[2]):
                    line = pps.groups()[0] + ", " + pps.groups()[1] + pps.groups()[2]
                else:
                    line = pps.groups()[0] + ", " + pps.groups()[1] + ", " + pps.groups()[2]
            sectionlines.append(maketitlecase(line))
            sectionlines.append("")
            firstline = False
        elif re.search(headerpattern, line):
            line = str(sectionctr) + ". " + maketitlecase(line)
            pps = re.search(parenthesispattern, line)
            if pps:
                if re.search(startperiodpattern, pps.groups()[2]):
                    line = pps.groups()[0] + ", " + pps.groups()[1] + pps.groups()[2]
                else:
                    line = pps.groups()[0] + ", " + pps.groups()[1] + ", " + pps.groups()[2]
            sectionlines.append("") # section header should have an empty line before it
            sectionlines.append(maketitlecase(line))
            sectionlines.append("") # section header should have an empty line after it as well.
            headers.append(line)
            sectionctr += 1
        elif re.search(emptypattern, line):
            continue # skip empty lines
        else:
            # If a line contains 5 or less words, then it is possibly a bulleted point. 
            # Add a period after each such line so that they have a small silence before 
            # and after them in the speech.
            pps = re.search(parenthesispattern, line)
            if pps:
                if re.search(startperiodpattern, pps.groups()[2]):
                    line = pps.groups()[0] + ", " + pps.groups()[1] + pps.groups()[2]
                else:
                    line = pps.groups()[0] + ", " + pps.groups()[1] + ", " + pps.groups()[2]
            words = line.split(" ")
            if words.__len__() <= 5:
                line += "."
            sectionlines.append(line)
    # At this point we should be having at least 2 header lines. 
    # If that is not the case, then we should do a second pass on
    # the content to identify a few more headers. The minimum 
    # number of headers is 2 because if it were 1 then we wouldn't
    # be able to create a new video by concatenating 2 videos, and
    # that could lead to charges of plagiarism.
    if headers.__len__() < 2:
        """
        Define more rules to identify headers. 
        These rules need to be a bit more inclusive
        than the rules in the previous pass.
        Rule #1: A line containing a full sentence 
        from start to period may be considered as a header.
        Rule #2: Top 5 lines with the highest number
        of keywords would be considered as headers.
        Note: We use a spaCy model to identify keywords.
        """
        def getcount(e):
            try:
                return e['count']
            except:
                return 0
        keywords = set(get_hotwords(textcontent))
        top10list = Counter(keywords).most_common(10)
        top10kw = []
        for item in top10list:
            top10kw.append(item[0])
        # Iterate over each line and identify 5 lines with the max number of keywords.
        kwcounts = [] # Keep in mind that the empty lines would be considered too.
        alllines = textcontent.split("\n")
        repairedlines = []
        # Join all lines ending with comma (,) or hyphen (-) characters. Basically repair lines that are broken.
        endcommahyphenpattern = re.compile("[,\-]\s*$")
        linectr = 0
        for _ in range(0, alllines.__len__()):
            if alllines.__len__() <= linectr:
                break
            line = alllines[linectr]
            if re.search(endcommahyphenpattern, line) and alllines.__len__() > linectr:
                line = line + alllines[linectr+1]
                linectr += 2
            else:
                linectr += 1
            repairedlines.append(line)
        linectr = 1
        for line in repairedlines:
            kwcnt = 0
            linelower = line.lower()
            # Find how many times each keyword appears in the line.
            for kw in top10kw:
                kwpattern = re.compile("\s+%s[\s,\.;]{0,1}"%kw, re.IGNORECASE)
                ll = re.findall(kwpattern, linelower)
                kwcnt += ll.__len__()
            kwcounts.append({'count' : kwcnt, 'index' : linectr})
            linectr += 1
        # So now kwcounts is a list of keyword counts indexed by line numbers (starting from line #1)
        # We will sort them on descending order of values and take the top 4 elements. These 4 lines
        # would be our header lines. Note: A segment/section should have both 'header' and 'content'.
        # Section header lines should be repeated in content if sections do not have any content after parsing.
        # Also, line number 2 (index 1) has to be used as header.
        kwcounts.sort(reverse=True, key=getcount)
        top5headerindices = ( kwcounts[0]['index'], kwcounts[1]['index'], kwcounts[2]['index'], kwcounts[3]['index'] )
        linectr = 0
        pointnumbers = 1
        sectionlines = []
        firstline = False
        for line in alllines: # Iterate over all lines again and format the text as per the header lines identified.
            line = line.replace("\n", "").replace("\r", "")
            if re.search(emptypattern, line):
                linectr += 1
                continue
            if linectr == 1 or linectr == 2 and not firstline:
                firstline = True
                pps = re.search(parenthesispattern, line)
                if pps:
                    if re.search(startperiodpattern, pps.groups()[2]):
                        line = pps.groups()[0] + ", " + pps.groups()[1] + pps.groups()[2]
                    else:
                        line = pps.groups()[0] + ", " + pps.groups()[1] + ", " + pps.groups()[2]
                line = str(pointnumbers) + ". " + maketitlecase(line)
                sectionlines.append("") # section header should have an empty line before it
                sectionlines.append(line)
                sectionlines.append("")
                pointnumbers += 1
            elif linectr in top5headerindices:
                pps = re.search(parenthesispattern, line)
                if pps:
                    if re.search(startperiodpattern, pps.groups()[2]):
                        line = pps.groups()[0] + ", " + pps.groups()[1] + pps.groups()[2]
                    else:
                        line = pps.groups()[0] + ", " + pps.groups()[1] + ", " + pps.groups()[2]
                line = str(pointnumbers) + ". " + maketitlecase(line)
                sectionlines.append("") # section header should have an empty line before it
                sectionlines.append(line)
                sectionlines.append("")
                pointnumbers += 1
            else:
                pps = re.search(parenthesispattern, line)
                if pps:
                    if re.search(startperiodpattern, pps.groups()[2]):
                        line = pps.groups()[0] + ", " + pps.groups()[1] + pps.groups()[2]
                    else:
                        line = pps.groups()[0] + ", " + pps.groups()[1] + ", " + pps.groups()[2]
                sectionlines.append(line)
            linectr += 1
    textfilename = os.path.basename(textfile)
    storyfile = textfilename.split(".")[0] + "_story.txt"
    fs = open(storyfile, "w")
    fs.write("\n".join(sectionlines))
    fs.close()
    return storyfile


def get_hotwords(text):
    """
    Function to identify keywords in the text content.
    """
    nlp = spacy.load("en_core_web_sm") # Load spacy model
    result = []
    pos_tag = ['PROPN', 'ADJ', 'NOUN'] 
    doc = nlp(text.lower()) 
    for token in doc:
        if(token.text in nlp.Defaults.stop_words or token.text in punctuation):
            continue
        if(token.pos_ in pos_tag):
            result.append(token.text)
    return result


"""
Function to make a line of text to title case with 
the exception of words that are entirely in uppercase.
"""
def maketitlecase(line):
    wordslist = line.split(" ")
    allupperpattern = re.compile("^[A-Z\d\:\?\/\-\,;_]+$")
    newwords = []
    for word in wordslist:
        if re.search(allupperpattern, word):
            newwords.append(word)
        else:
            newword = word.title()
            newwords.append(newword)
    newline = " ".join(newwords)
    return newline


def addtextonmp4stream(mp4file, textstring, outputmp4):
    textparts = textstring.split(".") # Check if it is multi-sentence text... we create a .srt file  for using it as subtitle text.
    subtitlesfile = "./subtitles.srt"
    fs = open(subtitlesfile, "w")
    ts = 0
    tf = 0
    ctr = 1
    dt = 5
    emptyspacespattern = re.compile("^\s*$")
    for t in textparts:
        if re.search(emptyspacespattern, t):
            continue
        if "\n" in t:
            t_t = t.split("\n")
            t = " ".join(t_t)
        words = t.split(" ")
        tf = ts + 3
        if words.__len__() > 8: # If number of words in the line is greater than 8...
            tf = ts+dt # .. the time for which it would be shown is 8 seconds.
        else:
            pass # .. else, it would be visible for 3 seconds only.
        tstr = "%s\n00:00:%s,000 --> 00:00:%s,000\n<font color='&Haa0000&'>%s</font>\n\n"%(ctr, ts, tf, t)
        ts = tf
        ctr += 1
        fs.write(tstr)
    fs.close()
    #cmd = "ffmpeg -y -i %s -vf \"drawtext=text='%s':y=(h-text_h)/2:x=w-(t-1.5)*w/5.5:font='DejaVuSans-Bold':fontcolor=black:fontsize=40:\" -codec:a copy %s"%(mp4file, textstring, outputmp4)
    cmd = "ffmpeg -y -i %s -vf subtitles=%s:force_style='Fontname=DejaVuSans-Bold' -codec:a copy %s"%(mp4file, subtitlesfile, outputmp4)
    try:
        retcode = subprocess.call(cmd, shell=True)
        if retcode != 0:
            print("\n\nffmpeg returned non-zero return code... %s\n\n"%retcode)
            textstring = "\n".join(textparts)
            cmd = "ffmpeg -y -i %s -vf \"drawtext=text='%s':y=(h-text_h)/2:x=w-(t-1.5)*w/5.5:font='DejaVuSans-Bold':fontcolor=black:fontsize=40:\"  -strict -2 -preset slow -pix_fmt yuv420p -codec:a copy %s"%(mp4file, textstring, outputmp4)
            subprocess.call(cmd, shell=True)
    except: # Simply copy the input file to the output file
        fi = open(mp4file, "rb")
        mp4content = fi.read()
        fi.close()
        fo = open(outputmp4, "wb")
        fo.write(mp4content)
        fo.close()
    try:
        os.unlink(subtitlesfile)
    except:
        pass
    return outputmp4


"""
This function cuts the input mp4 file at 'timespan' seconds from the start. outmp4 is the resulting mp4 stream.
"""
def trimvideostream(inputmp4, outmp4, timespan=60):
    # First thing, we move the moov atom to the begining of the file.
    moovfile = inputmp4.split(".")[0] + "_moov.mp4"
    cmd = "ffmpeg -y -i %s -c:v copy -c:a copy -movflags faststart %s"%(inputmp4, moovfile)
    subprocess.call(cmd, shell=True)
    tmin, tsec = "00", "00"
    if int(timespan) > 60:
        tmin = int(timespan/60)
        tsec = int((float(timespan)/60.00 - tmin) * 60)
    else:
        tmin = "00"
        tsec = timespan
    if str(tmin).__len__() < 2:
        tmin = "0" + str(tmin)
    if str(tsec).__len__() < 2:
        tsec = "0" + str(tsec)
    # Make a cut at 00:tmin:tsec (Should we care about hour?)
    cmd = "ffmpeg -y -ss 00:00:00 -i %s -c:v copy -c:a copy -to 00:%s:%s -avoid_negative_ts make_zero -strict -2 -preset slow -pix_fmt yuv420p %s"%(moovfile, tmin, tsec, outmp4)
    subprocess.call(cmd, shell=True)
    # Now get the duration of the video
    cmd = "ffprobe -loglevel error -show_entries format=duration -of default=nk=1:nw=1 \"%s\""%outmp4
    try:
        outstr = subprocess.check_output(cmd, shell=True)
        outstr = outstr.decode('utf-8')
        outstr = outstr.replace("\n", "").replace("\r", "")
        duration = round(float(outstr))
        # Now apply a fade out of 2 second at the end of the video. Both video and audio will fade out.
        fadeoutfile = outmp4.split(".")[0] + "_fadeout.mp4"
        fadestarttime = duration - 2
        cmd = "ffmpeg -y -i %s -filter_complex \"[0:v]fade=type=out:duration=2:start_time=%s[v];[0:a]afade=type=out:duration=2:start_time=%s[a]\" -map \"[v]\" -map \"[a]\" -strict -2 -preset slow -pix_fmt yuv420p %s"%(outmp4, str(fadestarttime), str(fadestarttime), fadeoutfile)
        subprocess.call(cmd, shell=True)
        # Rename the fadeout file to outmp4 file name.
        os.rename(fadeoutfile, outmp4)
    except: # For some reason, if we can't fade out, then return the original cut file.
        print("Could not add fade out in trimmed file. Error: %s"%sys.exc_info()[1].__str__())
    if not os.path.exists(outmp4) or os.path.getsize(outmp4) == 0:
        os.rename(moovfile, outmp4) # If outmp4 doesn't exist, then send back the moovfile as outmp4
    else:
        # Remove the moov file
        os.unlink(moovfile)
    return outmp4


def getaudioduration(audfile):
    cmd = "ffprobe -v error -select_streams a:0 -show_entries stream=duration -of default=noprint_wrappers=1:nokey=1 %s"%audfile
    try:
        outstr = subprocess.check_output(cmd, shell=True)
    except:
        print("Could not find the duration of '%s' - Error: %s"%(vidfile, sys.exc_info()[1].__str__()))
        return -1
    outstr = outstr.decode('utf-8')
    outstr = outstr.replace("\n", "").replace("\r", "")
    wspattern = re.compile("\s*", re.DOTALL)
    outstr = wspattern.sub("", outstr)
    if outstr == 'N/A':
        outstr = 0
    durationinseconds = float(outstr)
    return durationinseconds



def addvoiceoveraudio(inputmp4, audiofiles, outputmp4, timeslist):
    infilestr = ""
    delaystr = ""
    mixstr = ""
    delayctr = 1
    tctr = 0
    numfiles = audiofiles.__len__()
    for audiofile in audiofiles:
        infilestr += "-i %s "%audiofile # Note the space after '%s'. It is required.
        try:
            timeofstart = math.ceil(Fraction(timeslist[tctr])) * 1000
        except:
            continue
        delaystr += "[%s]adelay=%s[s%s];"%(delayctr, timeofstart, delayctr)
        mixstr += "[s%s]"%delayctr
        dur = getaudioduration(audiofile) * 1000
        availabletime = 0
        try:
            nexttimeofstart = math.ceil(Fraction(timeslist[tctr+1])) * 1000
            availabletime = nexttimeofstart - timeofstart
            if availabletime < dur:
                outaudiofile = audiofile.split(".")[0] + "_cut.wav"
                # Cut the audio file to make dur = availabletime
                cutcmd = "ffmpeg -y -ss 00 -i %s -to %s -c copy %s"%(audiofile, availabletime, outaudiofile)
                subprocess.call(cutcmd, shell=True)
                if os.path.exists(outaudiofile):
                    os.unlink(audiofile)
                    os.rename(outaudiofile, audiofile)
                else:
                    print("Couldn't find resized audio file.")
        except:
            print("Error while trying to cut audio file: %s"%sys.exc_info()[1].__str__())
        delayctr += 1
        tctr += 1
    cmd = "ffmpeg -y -i %s %s -max_muxing_queue_size 9999 -filter_complex \"%s%samix=%s[a]\" -map 0:v -map \"[a]\" -preset ultrafast %s"%(inputmp4, infilestr, delaystr, mixstr, numfiles, outputmp4)
    try:
        subprocess.call(cmd, shell=True)
    except:
        print("Error in '%s' : %s"%(cmd, sys.exc_info()[1].__str__()))
    return outputmp4


def getaudiofromtext(textstr):
    voiceurl = "https://regios.org/wavenet/wavenet-gen.php"
    postdict = {"input" : textstr}
    postdata = urlencode(postdict) # Need to do this to get the length of the content
    httpheaders = {'accept' : 'audio/mpeg', 'accept-encoding' : 'gzip,deflate'}
    httpheaders['content-length'] = str(postdata.__len__())
    response = requests.post(voiceurl, data=postdict, headers=httpheaders, stream=True)
    if response.status_code == 200:
        outaudiofile = time.strftime("%Y%m%d%H%M%S_wavenet_audio",time.localtime()) + ".mp3"
        out = open(outaudiofile, "wb")
        response.raw.decode_content = True
        shutil.copyfileobj(response.raw, out)
        out.close()
        print("Successfully retrieved audio file")
    else:
        return None
    return outaudiofile



def getaudiofromtext_google(textstr):
    #wavenet_api_key = "5e1a71620551d6fe8f65bc7f0790c52f34bf2f16"
    #wavenet_api_key = "ffcdb1dc5dff7b6ee0a6559b533c04ab6716b874"
    client = texttospeech.TextToSpeechClient()
    synthesis_input = texttospeech.SynthesisInput(text=textstr)
    # British male voice options: en-GB-Wavenet-B, en-GB-Wavenet-D, en-GB-Standard-B, en-GB-Standard-D . Code for all of them is en-GB.
    voice = texttospeech.VoiceSelectionParams(language_code="en-GB", name="en-GB-Wavenet-B", ssml_gender=texttospeech.SsmlVoiceGender.MALE)
    audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.LINEAR16)
    response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
    outaudiofile = time.strftime(os.getcwd() + os.path.sep + "videos" + os.path.sep + "%Y%m%d%H%M%S",time.localtime()) + ".wav"
    if os.path.exists(outaudiofile):
        datetimepattern = re.compile("^([\w\/\\_\-]+)[\\\/]{1}(\d{14})$")
        dps = re.search(datetimepattern, outaudiofile.split(".")[0])
        if dps:
            basedir = dps.groups()[0]
            filename = dps.groups()[1]
            outaudiofile = basedir + os.path.sep + str(int(filename) + 1) + ".wav"
        else:
            outaudiofile = outaudiofile.split(".")[0] + "_2.wav"
    with open(outaudiofile, "wb") as out:
        out.write(response.audio_content)
    print('Audio content written to file "%s"'%outaudiofile)
    return outaudiofile


def getaudiofromtext_google_2(textstr):
    url = "https://texttospeech.googleapis.com/v1beta1/text:synthesize"
    data = { "input": {"text": textstr}, "voice": {"name":  "en-GB-Wavenet-B", "languageCode": "en-GB"}, "audioConfig": {"audioEncoding": "LINEAR16"} };
    headers = {"content-type": "application/json", "X-Goog-Api-Key": "ffcdb1dc5dff7b6ee0a6559b533c04ab6716b874", "Authorization" : "Bearer ffcdb1dc5dff7b6ee0a6559b533c04ab6716b874" }
    r = requests.post(url=url, json=data, headers=headers)
    content = r.content
    outaudiofile = time.strftime(os.getcwd() + os.path.sep + "videos" + os.path.sep + "%Y%m%d%H%M%S",time.localtime()) + ".wav"
    if os.path.exists(outaudiofile):
        datetimepattern = re.compile("^([\w\/\\_\-]+)[\\\/]{1}(\d{14})$")
        dps = re.search(datetimepattern, outaudiofile.split(".")[0])
        if dps:
            basedir = dps.groups()[0]
            filename = dps.groups()[1]
            outaudiofile = basedir + os.path.sep + str(int(filename) + 1) + ".wav"
        else:
            outaudiofile = outaudiofile.split(".")[0] + "_2.wav"
    with open(outaudiofile, "wb") as out:
        out.write(content)
    print('Audio content written to file "%s"'%outaudiofile)
    return outaudiofile


def list_youtube_videos(searchkey, maxresults=10):
    global DEVELOPER_KEY
    api_service_name = "youtube"
    api_version = "v3"
    
    youtube = googleapiclient.discovery.build(api_service_name, api_version, developerKey = DEVELOPER_KEY)
    request = youtube.search().list(
        part="id,snippet",
        type='video',
        q=searchkey,
        videoDuration='short',
        videoDefinition='high',
        maxResults=maxresults,
        fields="items(id(videoId),snippet(publishedAt,channelId,channelTitle,title,description))"
    )
    response = request.execute()
    videoslist = []
    for resp in response['items']:
        vidid = resp['id']['videoId']
        channelid = resp['snippet']['channelId']
        videoslist.append({'channelid' : channelid, 'videoid' : vidid})
    return videoslist


def downloadvideo(videourl, downloadpath):
    yt = YouTube(videourl)
    yt = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc().first()
    try:
        yt.download(downloadpath)
        #time.sleep(3) # Wait for 3 seconds for the file to get downloaded.
    except:
        print("Error: %s"%sys.exc_info()[1].__str__())
    videofiles = glob.glob(downloadpath + os.path.sep + "*.mp4")
    if videofiles.__len__() > 0:
        videopath = videofiles[0]
    else:
        videopath = ""
    newvideopath = videopath.replace(" ", "_")
    newvideopath = newvideopath.replace("(", "").replace(")", "").replace("?", "").replace(",", "").replace("&", "and").replace("'", "").replace('"', "")
    fv = open(videopath, "rb")
    vidcontent = fv.read()
    fv.close()
    fnv = open(newvideopath, "wb")
    fnv.write(vidcontent)
    fnv.close()
    os.unlink(videopath)
    return newvideopath


def readandsegmenttext(filename):
    if not os.path.exists(filename):
        return []
    fp = open(filename, "r")
    content = fp.read()
    fp.close()
    contentparts = content.split("\n")
    """
    Now, some rules: 
    1. Lines starting with numbers actually break the define segments.
    2. Content from lines starting with numbers should be considered for youtube search.
    3. Lines not starting with numbers are the content for the previous line with number.
    4. First line of the file is a header.
    5. Content in a line starting with a number should limited to a single line. It should not be spread over multiple lines.
    """
    header = contentparts[0]
    linestartwithnumberpattern = re.compile("^\d+\.?\s*", re.DOTALL)
    emptylinepattern = re.compile("^\s*$")
    segmentslist = []
    segment = None
    for line in contentparts[1:]:
        if re.search(emptylinepattern, line):
            continue # Skip empty lines
        lps = re.search(linestartwithnumberpattern, line)
        if lps:
            if segment is not None:
                segmentslist.append(segment)
            segmenthead = line
            segmenthead = linestartwithnumberpattern.sub("", line)
            #segment = {'header' : segmenthead, 'content' : ''}
            segment = {'header' : segmenthead, 'content' : segmenthead}
        else:
            segmentcontent = line
            if segment is not None:
                segment['content'] += "\n" + segmentcontent
            else:
                segment = {'header' : os.path.basename(filename).split(".")[0], 'content' : segmentcontent}
    # Append the last segment processed
    if segment is not None:
        segmentslist.append(segment)
    return segmentslist


"""
A normal English speaker speaks about 120 - 130 words per minute.
Source: https://www.omnicalculator.com/everyday-life/words-per-minute
However, based on tests with various storyblocks and their voice over
audio, I have set it to 100 wpm. Although this is not perfect, it 
provides the best experience with the subtitles and the voiceover track.
"""
def computetimespanfromcontent(content):
    wordslist = re.split(re.compile("\s+", re.DOTALL), content)
    noofwords = wordslist.__len__()
    timeperchunk = 5 # 5 seconds per chunk (which is 10 words)
    chunksize = 10
    chunkcount = noofwords/chunksize
    totaltime = chunkcount * timeperchunk # This is only a *very rough* estimate.
    if chunkcount > 5: # More than 50 words ...
        totaltime = totaltime - 3 # ... reduce 3 seconds from computed totaltime. This helps take care of time between sentences.
    return totaltime


def uploadvideo_apivideo(videofile, vidtitle, viddesc="", tagslist=["heart", "health"], vidscope=True):
    if not os.path.exists(videofile):
        print("Error: video file '%s' does not exist"%videofile)
        return False
    API_KEY = "3pfEK7nViNTSxvqZCbwZ2SrYXyneV7KJQiBU8XSgxXt"
    youclient = apivideo.AuthenticatedApiClient(API_KEY) # Uncomment for production use
    #youclient = apivideo.AuthenticatedApiClient(API_KEY, production=False)
    youclient.connect()
    videosapi = VideosApi(youclient)
    video_payload = {"title": "%s"%vidtitle, "description": "%s"%viddesc, "public": vidscope, "tags": tagslist}
    vidcreateresponse = videosapi.create(video_payload)
    print("Video Container: %s"%str(vidcreateresponse))
    try:
        videoid = vidcreateresponse["video_id"]
    except:
        print("Could not get video create response: %s"%sys.exc_info()[1].__str__())
        return False
    try:
        fv = open(videofile, "rb")
        videouploadresponse = videosapi.upload(videoid, fv)
        print("Uploaded Video: %s"%str(videouploadresponse))
        fv.close() # Closing file.
    except:
        print("Error uploading video: %s"%sys.exc_info()[1].__str__())
        return False
    return True


def __get_youtube_token():
    tokenhere = None
    if os.path.exists('youtube.data'):
        with open('youtube.data') as creds:
            tokenhere = creds.read()  # Change to reflect how the token data is reflected in your 'creds.data' file
    return tokenhere


def __put_youtube_token(token):
    ft = open('youtube.data', "w")
    ft.write(token)
    ft.close()


def uploadvideo_youtube(videofile, vidtitle, viddesc="", tagslist=["heart", "health"]):
    YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
    CLIENT_SECRETS_FILE = "client_secrets.json"
    YOUTUBE_API_SERVICE_NAME = "youtube"
    YOUTUBE_API_VERSION = "v3"
    VALID_PRIVACY_STATUSES = ("public", "private", "unlisted")
    MISSING_CLIENT_SECRETS_MESSAGE = """
WARNING: Please configure OAuth 2.0
To make this code run you will need to populate the client_secrets.json file
found at:

   %s

with information from the API Console
https://console.developers.google.com/

For more information about the client_secrets.json file format, please visit:
https://developers.google.com/api-client-library/python/guide/aaa_client_secrets
    """%os.path.abspath(os.path.join(os.path.dirname(__file__), CLIENT_SECRETS_FILE))
    flow = flow_from_clientsecrets(CLIENT_SECRETS_FILE, scope=YOUTUBE_UPLOAD_SCOPE, message=MISSING_CLIENT_SECRETS_MESSAGE)
    storage = Storage("storymerge-oauth2.json")
    credentials = storage.get()
    flow.redirect_uri = client.OOB_CALLBACK_URN
    authorize_url = flow.step1_get_authorize_url()
    if credentials is None or credentials.invalid:
        try:
            accesstoken = __get_youtube_token()
            if accesstoken is None:
                flags = argparser.parse_args(args=[]) # This is so that run_flow doesn't look for command line arguments.
                credentials = run_flow(flow, storage, flags)
                accesstoken = credentials.access_token
                __put_youtube_token(accesstoken)
            else:
                credentials = flow.step2_exchange(accesstoken, http=httplib2.Http())
            print('Youtube API authentication successful.')
        except:
            print("Authentication failed for Youtube API: %s"%sys.exc_info()[1].__str__())
            return None
    youtube = build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, http=credentials.authorize(httplib2.Http()))
    try:
        body=dict(snippet=dict(title=vidtitle, description=viddesc, tags=tagslist, categoryId=22), status=dict(privacyStatus=VALID_PRIVACY_STATUSES[0]))
        insert_request = youtube.videos().insert(part=",".join(body.keys()), body=body, media_body=MediaFileUpload(videofile, chunksize=-1, resumable=True))
    except HttpError as e:
        print("An HTTP error %d occurred during video upload to youtube:\n%s" % (e.resp.status, e.content))
        return None
    __resumable_upload_youtube(insert_request)
    return True


# Utility function to handle resumable upload of video to youtube.
def __resumable_upload_youtube(insert_request):
    RETRIABLE_STATUS_CODES = [500, 502, 503, 504]
    # Always retry when these exceptions are raised.
    #RETRIABLE_EXCEPTIONS = (httplib2.HttpLib2Error, IOError, httplib.NotConnected, httplib.IncompleteRead, httplib.ImproperConnectionState, httplib.CannotSendRequest, httplib.CannotSendHeader, httplib.ResponseNotReady, httplib.BadStatusLine)
    httplib2.RETRIES = 1
    MAX_RETRIES = 10
    response = None
    error = None
    retry = 0
    while response is None:
        try:
            print("Uploading file...")
            status, response = insert_request.next_chunk()
            if response is not None:
                if 'id' in response:
                    print("Video id '%s' was successfully uploaded." % response['id'])
                else:
                    exit("The upload failed with an unexpected response: %s" % response)
        except Exception as e:
            if e.resp.status in RETRIABLE_STATUS_CODES: 
                error = "A retriable HTTP error %d occurred:\n%s" % (e.resp.status, e.content)
            else:
                error = "A retriable error occurred: %s" % e.content
                raise Exception(error)
        if error is not None:
            print(error)
            retry += 1
            if retry > MAX_RETRIES:
                exit("No longer attempting to retry.")
            max_sleep = 2 ** retry
            sleep_seconds = random.random() * max_sleep
            print("Sleeping %f seconds and then retrying..." % sleep_seconds)
            time.sleep(sleep_seconds)


def getstorymetadata(storyfile):
    if not os.path.exists(storyfile):
        print("Could not find story at '%s'"%storyfile)
        return []
    fs = open(storyfile, "r")
    storycontent = fs.read()
    fs.close()
    storylines = storyfile.split("\n")
    storytitle = ""
    segheadpattern = re.compile("^\d+\.?\s+")
    if storylines.__len__() == 0:
        return []
    storytitle = storylines[0]
    storytitle = segheadpattern.sub("", storytitle)
    linectr = 1
    while storytitle == "":
        storytitle = storylines[linectr]
        storytitle = segheadpattern.sub("", storytitle)
        linectr += 1
    try:
        storydesc = storylines[linectr]
    except:
        storydesc = storylines[linectr-1]
    storytags = []
    lineparts = storytitle.split(" ")
    for word in lineparts:
        # TODO: Figure out a better way of excluding non-proper-noun words.
        if word.lower() in ["is", "are", "the", "a", "an", "high", "low", "big", "small", "good", "bad", "best", "worst", "worse", "better", "if", "else", "of", "for", "from", "to", "till", "until", "find", "look", "lost", "found", "what", "when", "why", "where", "which", "do", "done", "did", "does", "yes", "no", "not", "may be", "none", "man", "woman", "male", "female", "boy", "girl", "men", "women", "be", "will", "would", "should", "shall", "will", "won't", "aren't", "isn't", "wouldn't", "shouldn't", "couldn't", "buy", "bought", "sell", "sold", "sale", "purchase", "before", "after", "up", "down", "middle", "centre", "between", "out", "outside", "include", "exclude", "inclusive", "exclusive", "except", "in", "out", "left", "right", "between", "this", "that", "these", "those", "they", "them", "thus", "so", "but", "how", "high", "low", "either", "or", "neither", "nor", "must", "may", "has", "had", "have", "hasn't", "haven't", "hadn't", "with", "without", "here", "there"]:
            continue # Just skip the above words
        storytags.append(word)
    return [storytitle, storydesc, storytags]




if __name__ == "__main__":
    textfile = os.getcwd() + os.path.sep + "test-input.txt"
    videotitle = ""
    if sys.argv.__len__() > 1:
        textfile = sys.argv[1]
    if not os.path.exists(textfile):
        print("Could not find input text block. Quitting.\n")
        sys.exit()
    if sys.argv.__len__() > 2:
        videotitle = sys.argv[2]
    # Get textfile and convert it into story format
    try:
        storyfile = createstoryfile(textfile)
    except:
        print("Could not generate story file. Error: %s"%sys.exc_info()[1].__str__())
        storyfile = None
    if storyfile is None or not os.path.exists(storyfile):
        print("No story file created. Exiting...")
        sys.exit()
    segmentslist = readandsegmenttext(storyfile)
    vidpath = os.getcwd() + os.path.sep + "videos"
    if not os.path.isdir(vidpath):
        os.makedirs(vidpath, 0o777)
    outpath = vidpath + os.path.sep + "outvideo.mp4"
    uniquedict = {}
    timeslist = [0, ]
    for segment in segmentslist:
        videoslist = list_youtube_videos(segment['header'], 3) # Get 3 video links: sometimes one of the links could be non-mp4 file.
        if not os.path.exists(vidpath):
            os.makedirs(vidpath)
        for vid in videoslist:
            if vid['videoid'] in uniquedict.keys():
                continue
            videourl = "https://www.youtube.com/watch?v=" + vid['videoid']
            downloadpath = vidpath + os.path.sep + vid['videoid']
            videopath = downloadvideo(videourl, downloadpath)
            vflag = 0
            if not os.path.exists(outpath):
                videowithtextpath = videopath.split(".")[0] + "_wtxt.mp4"
                segmentcontent = segment['content']
                addtextonmp4stream(videopath, segmentcontent, videowithtextpath)
                # Chop stream after ts seconds.. and send it to a new file.
                choppedvideopath = videowithtextpath.split(".")[0] + "_trmd.mp4"
                ts = computetimespanfromcontent(segmentcontent)
                nextvideostarttime = timeslist[-1] + ts + 0.5 # Start of subtitles will be half a second after the video starts
                timeslist.append(nextvideostarttime)
                trimvideostream(videowithtextpath, choppedvideopath, ts)
                fv = open(choppedvideopath, "rb")
                vidcontent = fv.read()
                fv.close()
                fo = open(outpath, "wb")
                fo.write(vidcontent)
                fo.close()
                vflag = 1
            else:
                videowithtextpath = videopath.split(".")[0] + "_wtxt.mp4"
                segmentcontent = segment['content']
                # Add text on stream
                addtextonmp4stream(videopath, segmentcontent, videowithtextpath)
                # Chop stream after ts seconds.. and send it to a new file.
                choppedvideopath = videowithtextpath.split(".")[0] + "_trmd.mp4"
                ts = computetimespanfromcontent(segmentcontent)
                nextvideostarttime = timeslist[-1] + ts + 0.5 # Start of subtitles will be half a second after the video starts
                trimvideostream(videowithtextpath, choppedvideopath, ts)
                outpathparts = outpath.split(".")
                newoutpath = outpathparts[0] + "_tmp.mp4"
                try:
                    # Not all streams can be trimmed... so if we don't have a trimmed file, we use the entire file with text.
                    if os.path.exists(choppedvideopath) and os.path.getsize(choppedvideopath) > 0:
                        newoutpath = va_concatmp4streams(outpath, choppedvideopath, newoutpath)
                    else:
                        newoutpath = va_concatmp4streams(outpath, videowithtextpath, newoutpath)
                    if newoutpath is None: # Error occurred during execution of command
                        continue
                    timeslist.append(nextvideostarttime)
                    fv = open(newoutpath, "rb")
                    vidcontent = fv.read()
                    fv.close()
                    fo = open(outpath, "wb")
                    fo.write(vidcontent)
                    fo.close()
                    os.unlink(newoutpath)
                    vflag = 1
                except:
                    print("Error: %s"%sys.exc_info()[1].__str__())
                    vflag = 0
                    outsize = os.path.getsize(outpath)
                    if outsize == 0: # This is the first output from stream... somehow, the actual first output was not dumped in the outfile.
                        fwt = open(choppedvideopath, "rb")
                        vwtcontent = fwt.read()
                        fwt.close()
                        fo = open(outpath, "wb")
                        fo.write(vwtcontent)
                        fo.close()
                    else:
                        pass
            try:
                os.unlink(videowithtextpath)
                os.unlink(choppedvideopath)
            except:
                pass
            if vflag == 1:
                uniquedict[vid['videoid']] = 1
                break
    # Get the audio from google speech to text
    segmentslist = readandsegmenttext(storyfile)
    audiofiles = []
    for segment in segmentslist:
        segtext = segment['content']
        if segtext.__len__() <= 2: # If content is less than 2 characters, use the header as the content
            continue
        inaudio = getaudiofromtext_google(segtext)
        if not inaudio or os.path.getsize(inaudio) < 1000: # inaudio file size less than 1kb
            print("Retrying to get audio again")
            os.unlink(inaudio)
            inaudio = getaudiofromtext_google(segtext) # Try once more...
            if not inaudio or os.path.getsize(inaudio) < 1000:
                print("Failed! Could not retrieve audio from the source")
                continue
        audiofiles.append(inaudio)
    outvoiceoverpath = outpath.split(".")[0] + "_vo.mp4"
    addvoiceoveraudio(outpath, audiofiles, outvoiceoverpath, timeslist)
    for audiofile in audiofiles:
        os.unlink(audiofile)
    try:
        os.unlink(outpath)
        os.rename(outvoiceoverpath, outpath)
    except:
        print("Error: %s"%sys.exc_info()[1].__str__())        
    print("\n\nOutput file: %s"%outpath)
    videodescription = ""
    videotags = []
    metadatalist = getstorymetadata(storyfile)
    if metadatalist.__len__() == 0:
        print("Error getting metadata from story file. Can't upload video.")
        sys.exit(1)
    if videotitle == "":
        videotitle = metadatalist[0]
    videodescription = metadatalist[1]
    videotags = metadatalist[2]
    uploadvideo_youtube(outpath, videotitle, videodescription, videotags)


# $> export GOOGLE_APPLICATION_CREDENTIALS=./storymerge-775cc31bde1f.json
# Run: python storymerge.py "/home/supmit/work/storymerge/real-input.txt"
# OR
# Run: python storymerge.py <story text file path> "<Story title>"
# Developer: Supriyo Mitra
# Date: 03-08-2022
"""
References:
https://stackoverflow.com/questions/17623676/text-on-video-ffmpeg
https://superuser.com/questions/1026763/scrolling-from-right-to-left-in-ffmpeg-drawtext/1026814#1026814
https://shotstack.io/learn/use-ffmpeg-to-trim-video/
https://askubuntu.com/questions/1128754/how-do-i-add-a-1-second-fade-out-effect-to-the-end-of-a-video-with-ffmpeg
https://video.stackexchange.com/questions/16516/ffmpeg-first-second-of-cut-video-part-freezed
https://superuser.com/questions/277642/how-to-merge-audio-and-video-file-in-ffmpeg
https://cloud.google.com/speech-to-text/docs/encoding
https://www.analyticsvidhya.com/blog/2022/03/keyword-extraction-methods-from-documents-in-nlp/
https://stackoverflow.com/questions/54699541/how-to-use-googles-text-to-speech-api-in-python
"""


