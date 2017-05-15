# coding: utf-8
# Copyright 2014 Globo.com Player authors. All rights reserved.
# Use of this source code is governed by a MIT License
# license that can be found in the LICENSE file.

import iso8601
import datetime
import itertools
import re
from m3u8 import protocol

'''
http://tools.ietf.org/html/draft-pantos-http-live-streaming-08#section-3.2
http://stackoverflow.com/questions/2785755/how-to-split-but-ignore-separators-in-quoted-strings-in-python
'''
ATTRIBUTE_LIST_PATTERN = re.compile(r'''((?:[^,"']|"[^"]*"|'[^']*')+)''')


def cast_date_time(value):
    return iso8601.parse_date(value)


def format_date_time(value):
    return value.isoformat()


class ParseError(Exception):

    def __init__(self, lineno, line):
        self.lineno = lineno
        self.line = line

    def __str__(self):
        return 'Syntax error in manifest on line %d: %s' % (self.lineno, self.line)


def parse(content, strict=False):
    """
    Given a M3U8 playlist content returns a dictionary with all data found
    :type content: str
    :type strict: bool
    :rtype: dict
    """
    data = {
        'media_sequence': 0,
        'is_variant': False,
        'is_endlist': False,
        'is_i_frames_only': False,
        'is_independent_segments': False,
        'playlist_type': None,
        'playlists': [],
        'segments': [],
        'iframe_playlists': [],
        'media': [],
        'keys': [],
    }

    state = {
        'expect_segment': False,
        'expect_playlist': False,
        'current_key': None,
    }

    lineno = 0
    for line in string_to_lines(content):
        lineno += 1
        line = line.strip()

        if line.startswith(protocol.ext_x_byterange):
            _parse_byterange(line, state)
            state['expect_segment'] = True

        elif line.startswith(protocol.ext_x_targetduration):
            _parse_simple_parameter(line, data, float)

        elif line.startswith(protocol.ext_x_media_sequence):
            _parse_simple_parameter(line, data, int)

        elif line.startswith(protocol.ext_x_program_date_time):
            _, program_date_time = _parse_simple_parameter_raw_value(line, cast_date_time)
            if not data.get('program_date_time'):
                data['program_date_time'] = program_date_time
            state['current_program_date_time'] = program_date_time

        elif line.startswith(protocol.ext_x_discontinuity):
            state['discontinuity'] = True

        elif line.startswith(protocol.ext_x_cue_out):
            _parse_cueout(line, state)
            state['cue_out'] = True
            state['cue_start'] = True

        elif line.startswith(protocol.ext_x_cue_out_start):
            _parse_cueout_start(line, state, string_to_lines(content)[lineno - 2])
            state['cue_out'] = True
            state['cue_start'] = True

        elif line.startswith(protocol.ext_x_cue_span):
            state['cue_out'] = True
            state['cue_start'] = True

        elif line.startswith(protocol.ext_x_version):
            _parse_simple_parameter(line, data)

        elif line.startswith(protocol.ext_x_allow_cache):
            _parse_simple_parameter(line, data)

        elif line.startswith(protocol.ext_x_key):
            key = _parse_key(line)
            state['current_key'] = key
            if key not in data['keys']:
                data['keys'].append(key)

        elif line.startswith(protocol.extinf):
            _parse_extinf(line, data, state, lineno, strict)
            state['expect_segment'] = True

        elif line.startswith(protocol.ext_x_stream_inf):
            state['expect_playlist'] = True
            _parse_stream_inf(line, data, state)

        elif line.startswith(protocol.ext_x_i_frame_stream_inf):
            _parse_i_frame_stream_inf(line, data)

        elif line.startswith(protocol.ext_x_media):
            _parse_media(line, data, state)

        elif line.startswith(protocol.ext_x_playlist_type):
            _parse_simple_parameter(line, data)

        elif line.startswith(protocol.ext_i_frames_only):
            data['is_i_frames_only'] = True

        elif line.startswith(protocol.ext_is_independent_segments):
            data['is_independent_segments'] = True

        elif line.startswith(protocol.ext_x_endlist):
            data['is_endlist'] = True

        elif line.startswith(protocol.ext_x_map):
            quoted_parser = remove_quotes_parser('uri')
            segment_map_info = _parse_attribute_list(protocol.ext_x_map, line, attribute_parser=quoted_parser)
            data['segment_map'] = segment_map_info

        # Comments and whitespace
        elif line.startswith('#'):
            # comment
            pass

        elif line.strip() == '':
            # blank lines are legal
            pass

        elif state['expect_segment']:
            _parse_ts_chunk(line, data, state)
            state['expect_segment'] = False

        elif state['expect_playlist']:
            _parse_variant_playlist(line, data, state)
            state['expect_playlist'] = False

        elif strict:
            raise ParseError(lineno, line)

    return data


def _parse_key(line):
    """
    :param line: #EXT-X-KEY:METHOD=AES-128,URI="../key.bin", IV=0X10ef8f758ca555115584bb5b3c687f52
    :rtype: dict
    """
    params = ATTRIBUTE_LIST_PATTERN.split(line.replace(protocol.ext_x_key + ':', ''))[1::2]
    key = {}
    for param in params:
        name, value = param.split('=', 1)
        key[normalize_attribute(name)] = remove_quotes(value)
    return key


def _parse_extinf(line, data, state, lineno, strict):
    """
    :param line: frozenset(['#EXTINF:5220,'])
    :type data: dict
    :type state: dict
    :type lineno: int
    :type strict: bool
    :rtype: None
    """
    chunks = line.replace(protocol.extinf + ':', '').split(',')
    if len(chunks) == 2:
        duration, title = chunks
    elif len(chunks) == 1:
        if strict:
            raise ParseError(lineno, line)
        else:
            duration = chunks[0]
            title = ''
    if 'segment' not in state:
        state['segment'] = {}
    state['segment']['duration'] = float(duration)
    state['segment']['title'] = remove_quotes(title)


def _parse_ts_chunk(line, data, state):
    """
    :param line: URI to .ts segment
    :type data: dict
    :type state: dict
    :rtype: None
    """
    segment = state.pop('segment')
    if state.get('current_program_date_time'):
        segment['program_date_time'] = state['current_program_date_time']
        state['current_program_date_time'] += datetime.timedelta(seconds=segment['duration'])
    segment['uri'] = line
    segment['cue_out'] = state.pop('cue_out', False)
    if state.get('current_cue_out_scte35'):
        segment['scte35'] = state['current_cue_out_scte35']
        segment['scte35_duration'] = state['current_cue_out_duration']
    segment['discontinuity'] = state.pop('discontinuity', False)
    if state.get('current_key'):
        segment['key'] = state['current_key']
    else:
        # For unencrypted segments, the initial key would be None
        if None not in data['keys']:
            data['keys'].append(None)
    data['segments'].append(segment)


def _parse_attribute_list(prefix, line, attribute_parser):
    """
    :param prefix: '#EXT-X-STREAM-INF'
    :param line: '#EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=445000,RESOLUTION=512x288,CODECS="avc1.77.30, mp4a.40.5"'
    :param attribute_parser: {attr_name: function, 'program_id': int, ...}
    :return: {program_id: 1, ...}
    """
    params = ATTRIBUTE_LIST_PATTERN.split(line.replace(prefix + ':', ''))[1::2]

    attributes = {}
    for param in params:
        name, value = param.split('=', 1)
        name = normalize_attribute(name)

        if name in attribute_parser:
            value = attribute_parser[name](value)

        attributes[name] = value

    return attributes


def _parse_stream_inf(line, data, state):
    """
    :param line: '#EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=445000,RESOLUTION=512x288,CODECS="avc1.77.30, mp4a.40.5"'
    :type data: dict
    :type state: dict
    :rtype: None
    """
    data['is_variant'] = True
    data['media_sequence'] = None
    atribute_parser = remove_quotes_parser('codecs', 'audio', 'video', 'subtitles')
    atribute_parser["program_id"] = int
    atribute_parser["bandwidth"] = lambda x: int(float(x))
    atribute_parser["average_bandwidth"] = int
    state['stream_info'] = _parse_attribute_list(protocol.ext_x_stream_inf, line, atribute_parser)


def _parse_i_frame_stream_inf(line, data):
    """
    :param line: '#EXT-X-I-FRAME-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=151288,RESOLUTION=624x352,CODECS="avc1.4d001f",
                  URI="video-800k-iframes.m3u8"'
    :type data: dict
    :rtype: None
    """
    atribute_parser = remove_quotes_parser('codecs', 'uri')
    atribute_parser["program_id"] = int
    atribute_parser["bandwidth"] = int
    iframe_stream_info = _parse_attribute_list(protocol.ext_x_i_frame_stream_inf, line, atribute_parser)
    iframe_playlist = {'uri': iframe_stream_info.pop('uri'),
                       'iframe_stream_info': iframe_stream_info}

    data['iframe_playlists'].append(iframe_playlist)


def _parse_media(line, data, state):
    """
    :param line: '#EXT-X-MEDIA:URI="chinese/ed.ttml",TYPE=SUBTITLES,GROUP-ID="subs",LANGUAGE="zho",NAME="Chinese",
                  AUTOSELECT=YES,FORCED=NO'
    :type data: dict
    :rtype: None
    """
    quoted = remove_quotes_parser('uri', 'group_id', 'language', 'name', 'characteristics')
    media = _parse_attribute_list(protocol.ext_x_media, line, quoted)
    data['media'].append(media)


def _parse_variant_playlist(line, data, state):
    """
    :param line: 'index_0_av.m3u8?e=b471643725c47acd'
    :type data: dict
    :type state: dict
    :rtype: None
    """
    playlist = {'uri': line,
                'stream_info': state.pop('stream_info')}

    data['playlists'].append(playlist)


def _parse_byterange(line, state):
    """
    :param line: '#EXT-X-BYTERANGE:9400@376'
    :type state: dict
    :rtype: None
    """
    if 'segment' not in state:
        state['segment'] = {}
    state['segment']['byterange'] = line.replace(protocol.ext_x_byterange + ':', '')


def _parse_simple_parameter_raw_value(line, cast_to=str, normalize=False):
    """
    :param line: '#EXT-X-PARAM-NAME:param_value'
    :type cast_to: callable
    :type normalize: bool
    :return: param_name, cast_to(param_value)
    """
    param, value = line.split(':', 1)
    param = normalize_attribute(param.replace('#EXT-X-', ''))
    if normalize:
        value = normalize_attribute(value)
    return param, cast_to(value)


def _parse_and_set_simple_parameter_raw_value(line, data, cast_to=str, normalize=False):
    """
    :param line: '#EXT-X-PARAM-NAME:param_value'
    :type data: dict
    :type cast_to: function
    :type normalize: bool
    :return: parameter casted with 'cast_to' to value
    """
    param, value = _parse_simple_parameter_raw_value(line, cast_to, normalize)
    data[param] = value
    return data[param]


def _parse_simple_parameter(line, data, cast_to=str):
    """
    :type line: str 
    :type data: dict 
    :type cast_to: callable
    :rtype: dict 
    """
    return _parse_and_set_simple_parameter_raw_value(line, data, cast_to, True)


def _parse_cueout(line, state):
    """
    :param line: '#EXT-X-CUE-OUT-CONT:CAID=0x000000002310E3A8,ElapsedTime=161,Duration=181'
    :type state: dict
    :rtype: None
    """
    param, value = line.split(':', 1)
    res = re.match('.*Duration=(.*),SCTE35=(.*)$', value)
    if res:
        state['current_cue_out_duration'] = res.group(1)
        state['current_cue_out_scte35'] = res.group(2)


def _cueout_elemental(line, state, prev_line):
    """
    :param line: '#EXT-X-CUE-OUT:DURATION=366,ID=16777323,
                  CUE="/DAlAAAENOOQAP/wFAUBAABrf+//N25XDf4B9p/gAAEBAQAAxKni9A=="'
    :param prev_line:
    :return: '/DAlAAAAAAAAAP/wFAUAAAABf+//wpiQkv4ARKogAAEBAQAAQ6sodg==', '50.000'
    """
    param, value = line.split(':', 1)
    res = re.match('.*EXT-OATCLS-SCTE35:(.*)$', prev_line)
    if res:
        return res.group(1), value
    else:
        return None


def _cueout_envivio(line, state, prev_line):
    """
    :param line: '#EXT-X-CUE-OUT:DURATION=366,ID=16777323,
                  CUE="/DAlAAAENOOQAP/wFAUBAABrf+//N25XDf4B9p/gAAEBAQAAxKni9A=="'
    :return: "/DAlAAAENOOQAP/wFAUBAABrf+//N25XDf4B9p/gAAEBAQAAxKni9A==", '366'
    """
    param, value = line.split(':', 1)
    res = re.match('.*DURATION=(.*),.*,CUE="(.*)"', value)
    if res:
        return res.group(2), res.group(1)
    else:
        return None


def _parse_cueout_start(line, state, prev_line):
    _cueout_state = _cueout_elemental(line, state, prev_line) or _cueout_envivio(line, state, prev_line)
    if _cueout_state:
        state['current_cue_out_scte35'] = _cueout_state[0]
        state['current_cue_out_duration'] = _cueout_state[1]


def string_to_lines(string):
    return string.strip().replace('\r\n', '\n').split('\n')


def remove_quotes_parser(*attrs):
    """
    :param attrs: <type 'tuple'>: ('codecs', 'audio', 'video', 'subtitles')
    :return: {attr: remove_quotes}
    """
    return dict(zip(attrs, itertools.repeat(remove_quotes)))


def remove_quotes(string):
    """
    Remove quotes from string.

    Ex.:
      "foo" -> foo
      'foo' -> foo
      'foo  -> 'foo

    """
    quotes = ('"', "'")
    if string and string[0] in quotes and string[-1] in quotes:
        return string[1:-1]
    return string


def normalize_attribute(attribute):
    return attribute.replace('-', '_').lower().strip()


def is_url(uri):
    return re.match(r'https?://', uri) is not None
