import os, sys, re, time
import datetime
import glob

import simplejson as json
import subprocess
import numpy as np
import pyaudio

import googleapiclient.discovery
from pytube import YouTube


def v_concatmp4streams(mp4file_1, mp4file_2, mp4outfile):
    cmd = "ffmpeg -y -i %s -i %s -filter_complex \"[0:v] [1:v] concat=n=2:v=1 [v]\" -map \"[v]\" %s"%(mp4file_1, mp4file_2, mp4outfile)
    subprocess.call(cmd, shell=True)
    return mp4outfile


def va_concatmp4streams(mp4file_1, mp4file_2, mp4outfile):
    cmd = "ffmpeg -y -i %s -i %s -filter_complex \"[0:v] [0:a] [1:v] [1:a] concat=n=2:v=1:a=1 [v] [a]\" -map \"[v]\" -map \"[a]\" %s"%(mp4file_1, mp4file_2, mp4outfile)
    subprocess.call(cmd, shell=True)
    return mp4outfile


def addtextonmp4stream(mp4file, textstring, outputmp4):
    #cmd = "ffmpeg -y -i %s -vf \"drawtext=text='%s':fontcolor=white:fontsize=20:box=1:boxcolor=black@0.5:boxborderw=5:x=(w-text_w)/2:y=(h-text_h)/2\" -codec:a copy %s"%(mp4file, textstring, outputmp4)
    textparts = textstring.split("\n") # Check if it is multiline text... if so, join it using asterisks ('*')
    if textparts.__len__() > 1:
        textstring = "  ".join(textparts)
    cmd = "ffmpeg -y -i %s -vf \"drawtext=text='%s':y=(h-text_h)/2:x=w-(t-1.5)*w/5.5:fontcolor=black:fontsize=40:\" -codec:a copy %s"%(mp4file, textstring, outputmp4)
    try:
        retcode = subprocess.call(cmd, shell=True)
        if retcode != 0:
            print("\n\nffmpeg returned non-zero return code... %s\n\n"%retcode)
            textstring = "\n".join(textparts)
            cmd = "ffmpeg -y -i %s -vf \"drawtext=text='%s':y=(h-text_h)/2:x=w-(t-1.5)*w/5.5:fontcolor=black:fontsize=40:\" -codec:a copy %s"%(mp4file, textstring, outputmp4)
            subprocess.call(cmd, shell=True)
    except: # Simply copy the input file to the output file
        fi = open(mp4file, "rb")
        mp4content = fi.read()
        fi.close()
        fo = open(outputmp4, "wb")
        fo.write(mp4content)
        fo.close()
    return outputmp4


def list_youtube_videos(searchkey, maxresults=10):
    api_service_name = "youtube"
    api_version = "v3"
    DEVELOPER_KEY = 'AIzaSyDK0xlWEzAf3IkE7WuKJYZnL-UWnDfHALw'
    #DEVELOPER_KEY = 'AIzaSyCjOk1a5NH26Qg-VYaFZW0RLJmDyVCnGQ8'
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
    newvideopath = newvideopath.replace("(", "").replace(")", "").replace("?", "").replace(",", "")
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
            segment['content'] += "\n" + segmentcontent
    # Append the last segment processed
    if segment is not None:
        segmentslist.append(segment)
    return segmentslist




if __name__ == "__main__":
    textfile = os.getcwd() + os.path.sep + "random-story-text.txt"
    #textfile = os.getcwd() + os.path.sep + "top-12-questions-about-hypertension.txt"
    #textfile = os.getcwd() + os.path.sep + "top-5-questions-about-cancer.txt"
    if sys.argv.__len__() > 1:
        textfile = sys.argv[1]
    segmentslist = readandsegmenttext(textfile)
    vidpath = os.getcwd() + os.path.sep + "videos"
    outpath = vidpath + os.path.sep + "outvideo.mp4"
    for segment in segmentslist:
        videoslist = list_youtube_videos(segment['header'], 3) # Get 3 video links: sometimes one of the links could be non-mp4 file.
        if not os.path.exists(vidpath):
            os.makedirs(vidpath)
        for vid in videoslist:
            videourl = "https://www.youtube.com/watch?v=" + vid['videoid']
            downloadpath = vidpath + os.path.sep + vid['videoid']
            videopath = downloadvideo(videourl, downloadpath)
            vflag = 0
            if not os.path.exists(outpath):
                videowithtextpath = videopath.split(".")[0] + "_wtxt.mp4"
                if segment['content'].__len__() > 100:
                    segmentcontent = segment['content'][:100] + "..." # Get first 100 characters
                else:
                    segmentcontent = segment['content']
                addtextonmp4stream(videopath, segmentcontent, videowithtextpath)
                fv = open(videowithtextpath, "rb")
                vidcontent = fv.read()
                fv.close()
                fo = open(outpath, "wb")
                fo.write(vidcontent)
                fo.close()
                vflag = 1
            else:
                videowithtextpath = videopath.split(".")[0] + "_wtxt.mp4"
                if segment['content'].__len__() > 100:
                    segmentcontent = segment['content'][:100] + "..." # Get first 100 characters
                else:
                    segmentcontent = segment['content']
                addtextonmp4stream(videopath, segmentcontent, videowithtextpath)
                outpathparts = outpath.split(".")
                newoutpath = outpathparts[0] + "_tmp.mp4"
                try:
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
                        fwt = open(videowithtextpath, "rb")
                        vwtcontent = fwt.read()
                        fwt.close()
                        fo = open(outpath, "wb")
                        fo.write(vwtcontent)
                        fo.close()
                    else:
                        pass
            try:
                os.unlink(videowithtextpath)
            except:
                pass
            if vflag == 1:
                break
    print("Done!")


"""
if __name__ == "__main__":
    textfile = os.getcwd() + os.path.sep + "top-12-questions-about-hypertension.txt"
    segmentslist = readandsegmenttext(textfile)
    vidpath = os.getcwd() + os.path.sep + "videos"
    outpath = vidpath + os.path.sep + "outvideo.mp4"
    videodirs = glob.glob(vidpath + os.path.sep + "*")
    for segment in segmentslist:
        #print(segment['header'] + " : " + segment['content'])
        if videodirs.__len__() == 0:
            break
        viddir = videodirs.pop()
        videoslist = glob.glob(viddir + os.path.sep + "*.mp4")
        if not os.path.exists(vidpath):
            os.makedirs(vidpath)
        for vid in videoslist:
            #videourl = "https://www.youtube.com/watch?v=" + vid['videoid']
            #downloadpath = vidpath + os.path.sep + vid['videoid']
            #videopath = downloadvideo(videourl, downloadpath)
            videopath = videoslist[0]
            if not os.path.exists(outpath):
                fv = open(videopath, "rb")
                vidcontent = fv.read()
                fv.close()
                fo = open(outpath, "wb")
                fo.write(vidcontent)
                fo.close()
            else:
                outpathparts = outpath.split(".")
                newoutpath = outpathparts[0] + "_tmp.mp4"
                newoutpath = va_concatmp4streams(outpath, videopath, newoutpath)
                fv = open(newoutpath, "rb")
                vidcontent = fv.read()
                fv.close()
                fo = open(outpath, "wb")
                fo.write(vidcontent)
                fo.close()
                os.unlink(newoutpath)
            break
    print("Done!")
"""
# Run: python storymerge.py "/home/supmit/work/storymerge/sometextfile.txt"
# OR
# Run: python storymerge.py
# Developed by Supriyo Mitra
# Date: 03-08-2022

