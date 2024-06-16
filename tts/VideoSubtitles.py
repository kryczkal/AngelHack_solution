import assemblyai as aai
from typing import List
from moviepy.editor import *
from datetime import timedelta
import srt_equalizer
from moviepy.video.tools.subtitles import SubtitlesClip
import configparser
import elTTS
from VideoEditor import get_audio_length


def __generate_subtitles_assemblyai(audio_path: str, voice: str, ASSEMBLY_AI_API_KEY: str) -> str:
    """
    Generates subtitles from a given audio file and returns the path to the subtitles.

    Args:
        audio_path (str): The path to the audio file to generate subtitles from.

    Returns:
        str: The generated subtitles
    """

    language_mapping = {
        "br": "pt",
        "id": "en",  # AssemblyAI doesn't have Indonesian
        "jp": "ja",
        "kr": "ko",
    }

    if voice in language_mapping:
        lang_code = language_mapping[voice]
    else:
        lang_code = voice

    aai.settings.api_key = ASSEMBLY_AI_API_KEY
    config = aai.TranscriptionConfig(language_code=lang_code)
    transcriber = aai.Transcriber(config=config)
    transcript = transcriber.transcribe(audio_path)
    subtitles = transcript.export_subtitles_srt()

    return subtitles


def __generate_subtitles_locally(sentences: List[str], audio_clips: List[AudioFileClip]) -> str:
    """
    Generates subtitles from a given audio file and returns the path to the subtitles.

    Args:
        sentences (List[str]): all the sentences said out loud in the audio clips
        audio_clips (List[AudioFileClip]): all the individual audio clips which will make up the final audio track
    Returns:
        str: The generated subtitles
    """

    def convert_to_srt_time_format(total_seconds):
        # Convert total seconds to the SRT time format: HH:MM:SS,mmm
        if total_seconds == 0:
            return "0:00:00,0"
        return str(timedelta(seconds=total_seconds)).rstrip('0').replace('.', ',')

    start_time = 0
    subtitles = []

    for i, (sentence, audio_clip) in enumerate(zip(sentences, audio_clips), start=1):
        duration = audio_clip.duration
        end_time = start_time + duration

        # Format: subtitle index, start time --> end time, sentence
        subtitle_entry = f"{i}\n{convert_to_srt_time_format(start_time)} --> {convert_to_srt_time_format(end_time)}\n{sentence}\n"
        subtitles.append(subtitle_entry)

        start_time += duration  # Update start time for the next subtitle

    return "\n".join(subtitles)


def generate_subtitles(audio_path: str, sentences: List[str], audio_clips: List[AudioFileClip], voice: str,
                       subtitles_path: str, ASSEMBLY_AI_API_KEY: str) -> str:
    """
    Generates subtitles from a given audio file and returns the path to the subtitles.

    Args:
        audio_path (str): The path to the audio file to generate subtitles from.
        sentences (List[str]): all the sentences said out loud in the audio clips
        audio_clips (List[AudioFileClip]): all the individual audio clips which will make up the final audio track

    Returns:
        str: The path to the generated subtitles.
    """

    def equalize_subtitles(srt_path: str, max_chars: int = 10) -> None:
        # Equalize subtitles
        srt_equalizer.equalize_srt_file(srt_path, srt_path, max_chars)

    if ASSEMBLY_AI_API_KEY is not None and ASSEMBLY_AI_API_KEY != "":
        print("[+] Creating subtitles using AssemblyAI")
        subtitles = __generate_subtitles_assemblyai(audio_path, voice, ASSEMBLY_AI_API_KEY)
    else:
        print("[+] Creating subtitles locally")
        subtitles = __generate_subtitles_locally(sentences, audio_clips)
        # print(colored("[-] Local subtitle generation has been disabled for the time being.", "red"))
        # print(colored("[-] Exiting.", "red"))
        # sys.exit(1)

    with open(subtitles_path, "w") as file:
        file.write(subtitles)

    # Equalize subtitles
    equalize_subtitles(subtitles_path)

    print("[+] Subtitles generated.", "green")

    return subtitles_path


def combine_videos(video_paths: List[str], max_duration: int, max_clip_duration: int, threads: int) -> str:
    """
    Combines a list of videos into one video and returns the path to the combined video.

    Args:
        video_paths (List): A list of paths to the videos to combine.
        max_duration (int): The maximum duration of the combined video.
        max_clip_duration (int): The maximum duration of each clip.
        threads (int): The number of threads to use for the video processing.

    Returns:
        str: The path to the combined video.
    """
    video_id = uuid.uuid4()
    combined_video_path = f"../temp/{video_id}.mp4"

    # Required duration of each clip
    req_dur = max_duration / len(video_paths)

    print(colored("[+] Combining videos...", "blue"))
    print(colored(f"[+] Each clip will be maximum {req_dur} seconds long.", "blue"))

    clips = []
    tot_dur = 0
    # Add downloaded clips over and over until the duration of the audio (max_duration) has been reached
    while tot_dur < max_duration:
        for video_path in video_paths:
            clip = VideoFileClip(video_path)
            clip = clip.without_audio()
            # Check if clip is longer than the remaining audio
            if (max_duration - tot_dur) < clip.duration:
                clip = clip.subclip(0, (max_duration - tot_dur))
            # Only shorten clips if the calculated clip length (req_dur) is shorter than the actual clip to prevent still image
            elif req_dur < clip.duration:
                clip = clip.subclip(0, req_dur)
            clip = clip.set_fps(30)

            # Not all videos are same size,
            # so we need to resize them
            if round((clip.w / clip.h), 4) < 0.5625:
                clip = crop(clip, width=clip.w, height=round(clip.w / 0.5625), \
                            x_center=clip.w / 2, \
                            y_center=clip.h / 2)
            else:
                clip = crop(clip, width=round(0.5625 * clip.h), height=clip.h, \
                            x_center=clip.w / 2, \
                            y_center=clip.h / 2)
            clip = clip.resize((1080, 1920))

            if clip.duration > max_clip_duration:
                clip = clip.subclip(0, max_clip_duration)

            clips.append(clip)
            tot_dur += clip.duration

    final_clip = concatenate_videoclips(clips)
    final_clip = final_clip.set_fps(30)
    final_clip.write_videofile(combined_video_path, threads=threads)

    return combined_video_path


def generate_video(combined_video_path: str, tts_path: str, subtitles_path: str, threads: int, subtitles_position: str,
                   output_file_path: str ,text_color: str):
    """
    This function creates the final video, with subtitles and audio.

    Args:
        combined_video_path (str): The path to the combined video.
        tts_path (str): The path to the text-to-speech audio.
        subtitles_path (str): The path to the subtitles.
        threads (int): The number of threads to use for the video processing.
        subtitles_position (str): The position of the subtitles.

    Returns:
        str: The path to the final video.
    """
    # Make a generator that returns a TextClip when called with consecutive
    generator = lambda txt: TextClip(
        txt,
        font="fonts/bold_font.ttf",
        fontsize=100,
        color=text_color,
        stroke_color="black",
        stroke_width=5,
    )

    # Split the subtitles position into horizontal and vertical
    horizontal_subtitles_position, vertical_subtitles_position = subtitles_position.split(",")

    # Burn the subtitles into the video
    subtitles = SubtitlesClip(subtitles_path, generator)
    result = CompositeVideoClip([
        VideoFileClip(combined_video_path),
        subtitles.set_pos((horizontal_subtitles_position, vertical_subtitles_position))
    ])

    # Add the audio
    audio = AudioFileClip(tts_path)
    result = result.set_audio(audio)

    result.write_videofile(output_file_path, 2)  # threads=threads or 2) we can set the number of threads being used

def get_sentences(script_path: str) -> List[str]:
    with open(script_path, 'r') as file:
        script = file.read()

    _sentences = script.split(".")
    return _sentences

def get_audio_clips(_sentences, _cnf):
    # generating audio files for each sentence
    _audio_clips = []
    for i in range(len(_sentences)):
        filename = f"audio_storage/sentence{i}.mp3"
        elTTS.TTS.generate_sentence(filename, _sentences[i], _cnf)
        audio_clip = AudioFileClip(filename)
        _audio_clips.append(audio_clip)
    return _audio_clips


if __name__ == "__main__":
    cnf = configparser.ConfigParser()
    cnf.read('config.ini')

    assemblyai_api_key = cnf['TTS_CONFIG']['ASSEMBLY_AI_API_KEY']
    audio_file_path = cnf['TTS_CONFIG']['AUDIO_PATH']
    subtitles_file_path = cnf['TTS_CONFIG']['SUBTITLES_PATH']
    video_file_path = cnf['TTS_CONFIG']['VIDEO_PATH']
    output_file_path = cnf['TTS_CONFIG']['OUTPUT_PATH']
    script_file_path = cnf['TTS_CONFIG']['SCRIPT_PATH']

    sentences = get_sentences(script_file_path)
    audio_clips = get_audio_clips(sentences, cnf)

    # commented for now to not lose tokens
    # tts = elTTS.TTS()
    # tts.generate(script_file_path)

    generate_subtitles(audio_file_path, sentences, audio_clips, "en", subtitles_file_path, assemblyai_api_key)
    generate_video(output_file_path, audio_file_path, subtitles_file_path, 1, "center,center",
                   output_file_path, "green")