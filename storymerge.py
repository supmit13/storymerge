import os, sys, re, time
import datetime
import glob
import shutil

import simplejson as json
import subprocess
import numpy as np
import urllib, requests
from urllib.parse import urlencode
from fractions import Fraction
import math

import googleapiclient.discovery
from pytube import YouTube
from google.cloud import texttospeech

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getcwd() + os.path.sep + "storymerge-775cc31bde1f.json"

"""
Dependencies: ffmpeg, python3, GOOGLE_APPLICATION_CREDENTIALS, pytube, googleapiclient
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
    #cmd = "ffmpeg -y -i %s -i %s -filter_complex \"[0:v] [0:a] [1:v] [1:a] concat=n=2:v=1:a=1 [v] [a]\" -map \"[v]\" -map \"[a]\" -strict -2 -preset slow -pix_fmt yuv420p %s"%(tmpfile1, mp4file_2, mp4outfile)
    cmd = "ffmpeg -i %s -i %s -filter_complex \"[0]setdar=16/9[a];[1]setdar=16/9[b]; [a][0:a][b][1:a]concat=n=2:v=1:a=1 [v] [a]\" -map \"[v]\" -map \"[a]\" -strict -2 -preset slow -pix_fmt yuv420p %s"%(tmpfile1, mp4file_2, mp4outfile)
    subprocess.call(cmd, shell=True)
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
    cmd = "ffmpeg -i %s -c:v copy -c:a copy -movflags faststart %s"%(inputmp4, moovfile)
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
    cmd = "ffmpeg -ss 00:00:00 -i %s -c:v copy -c:a copy -to 00:%s:%s -avoid_negative_ts make_zero -strict -2 -preset slow -pix_fmt yuv420p %s"%(moovfile, tmin, tsec, outmp4)
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
        cmd = "ffmpeg -i %s -filter_complex \"[0:v]fade=type=out:duration=2:start_time=%s[v];[0:a]afade=type=out:duration=2:start_time=%s[a]\" -map \"[v]\" -map \"[a]\" -strict -2 -preset slow -pix_fmt yuv420p %s"%(outmp4, str(fadestarttime), str(fadestarttime), fadeoutfile)
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
        timeofstart = math.ceil(Fraction(timeslist[tctr])) * 1000
        delaystr += "[%s]adelay=%s[s%s];"%(delayctr, timeofstart, delayctr)
        mixstr += "[s%s]"%delayctr
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
    client = texttospeech.TextToSpeechClient()
    synthesis_input = texttospeech.SynthesisInput(text=textstr)
    # British male voice options: en-GB-Wavenet-B, en-GB-Wavenet-D, en-GB-Standard-B, en-GB-Standard-D . Code for all of them is en-GB.
    voice = texttospeech.VoiceSelectionParams(language_code="en-GB", name="en-GB-Standard-B", ssml_gender=texttospeech.SsmlVoiceGender.MALE)
    audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.LINEAR16)
    response = client.synthesize_speech(input=synthesis_input, voice=voice, audio_config=audio_config)
    outaudiofile = time.strftime(os.getcwd() + os.path.sep + "videos" + os.path.sep + "%Y%m%d%H%M%S",time.localtime()) + ".wav"
    if os.path.exists(outaudiofile):
        outaudiofile = str(int(outaudiofile.split(".")[0]) + 1) + ".wav"
    with open(outaudiofile, "wb") as out:
        out.write(response.audio_content)
    print('Audio content written to file "%s"'%outaudiofile)
    return outaudiofile


def list_youtube_videos(searchkey, maxresults=10):
    api_service_name = "youtube"
    api_version = "v3"
    #DEVELOPER_KEY = 'AIzaSyDK0xlWEzAf3IkE7WuKJYZnL-UWnDfHALw'
    DEVELOPER_KEY = 'AIzaSyCjOk1a5NH26Qg-VYaFZW0RLJmDyVCnGQ8'
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
            segment = {'header' : segmenthead, 'content' : ''}
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


if __name__ == "__main__":
    textfile = os.getcwd() + os.path.sep + "test-input.txt"
    if sys.argv.__len__() > 1:
        textfile = sys.argv[1]
    if not os.path.exists(textfile):
        print("Could not find input text block. Quitting.\n")
        sys.exit()
    segmentslist = readandsegmenttext(textfile)
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
                timeslist.append(nextvideostarttime)
                trimvideostream(videowithtextpath, choppedvideopath, ts)
                outpathparts = outpath.split(".")
                newoutpath = outpathparts[0] + "_tmp.mp4"
                try:
                    # Not all streams can be trimmed... so if we don't have a trimmed file, we use the entire file with text.
                    if os.path.exists(choppedvideopath) and os.path.getsize(choppedvideopath) > 0:
                        newoutpath = va_concatmp4streams(outpath, choppedvideopath, newoutpath)
                    else:
                        newoutpath = va_concatmp4streams(outpath, videowithtextpath, newoutpath)
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
    segmentslist = readandsegmenttext(textfile)
    audiofiles = []
    for segment in segmentslist:
        segtext = segment['content']
        if segtext.__len__() < 2: # If content is less than 2 characters, we skip, since that would only be a '\r\n'
            tctr += 1
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
        print("ErrorAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA: %s"%sys.exc_info()[1].__str__())        
    print("\n\nOutput file: %s"%outpath)

# $> export GOOGLE_APPLICATION_CREDENTIALS=./storymerge-775cc31bde1f.json
# Run: python storymerge.py "/home/supmit/work/storymerge/real-input.txt"
# OR
# Run: python storymerge.py
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

"""


