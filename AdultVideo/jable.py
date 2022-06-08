import re
import time
import json
import random

import cloudscraper
import requests
from redis import Redis
from adultVideo.config import *
from bs4 import BeautifulSoup
from Crypto.Cipher import AES
from concurrent.futures.thread import ThreadPoolExecutor



def demo(video,headers=HEADERS):
    session = cloudscraper.create_scraper(
        browser={
            'browser': 'firefox',
            'platform': 'windows',
            'mobile': False
        }
    )
    resp = session.get(url=video['url'])
    if resp.status_code != 200:
        return {}
    html = resp.text
    soup = BeautifulSoup(html, 'html.parser')
    try:
        models = soup.find_all('a', class_='model')
        video['star'] = [m.find_next().attrs['title'] for m in models]
    except:
        video['star'] = []
    try:
        hash_tags = soup.find('h5', class_='tags h6-md').find_all('a')
        video['hash_tag'] = [h.get_text() for h in hash_tags]
    except:
        video['hash_tag'] = []
    pat = "hlsUrl = '(.*?)';"
    realUrl = re.compile(pat, re.S).findall(html)
    if realUrl:
        video['realUrl'] = realUrl[0]
        return video
    return {}

def test_add_tag():
    url = 'http://127.0.0.1:8000/api/tag/create/'
    tags_map = {
        '中文字幕': [],
        '制服誘惑': [],
        '角色劇情': [],
        '凌辱強暴': [],
        '衣着': ['絲襪', '黑絲', ],
        '环境': ['學校', '圖書館', '電車'],
        '动作': ['錄像', '媚藥', '出軌', '中出', ],
        '身份': ['少女', '老師', '痴漢', '人妻', '熟女', ],
        '身材': ['短髮', '美腿', '美尻', '巨乳', '絲襪美腿', ]
    }
    for key, value in tags_map.items():
        form = {'name': key}
        data = requests.post(url=url, json=form)
        result = data.json()
        print(result)
        group_id = result['data']['id']
        time.sleep(1)
        for v in value:
            form = {'name': v, 'group_id': group_id}
            data = requests.post(url=url, json=form)
            result = data.json()
            print('sub tag', result)
            if result['code'] != 0:
                continue
            time.sleep(1)


class JableSpider():
    def __init__(self):
        self.redis = Redis.from_url(REDIS_ROUTE['tags'],decode_responses=True)
        self.headers = HEADERS
        self.base_url = 'https://jable.tv/'
        self.category_url = TAG_URL['jable']
        self.session = cloudscraper.create_scraper(
            browser={
                'browser': 'firefox',
                'platform': 'windows',
                'mobile': False
            }
        )

    def get_categories_list(self):
        resp = self.session.get(url=self.category_url)
        print(resp.status_code)
        soup = BeautifulSoup(resp.text, 'html.parser')
        category_list = soup.find_all('div', class_='col-6 col-sm-4 col-lg-3')
        res = [{
            'tags': c.find('h4').get_text(),
            'href': c.find('a').attrs['href'],
        } for c in category_list]

        self.redis.set('jable', json.dumps(res))

    def get_video_list(self,tag_item):
        page = 1
        while True:
            url = f'{tag_item["href"]}?from={page}'
            resp = self.session.get(url)
            if resp.status_code != 200:
                break
            soup = BeautifulSoup(resp.text, 'html.parser')
            video_set = soup.find_all('div', class_='col-6 col-sm-4 col-lg-3')
            videos_data = []
            for v in video_set:
                video = {
                    'title': v.find('h6', class_='title').a.get_text(),
                    'url': v.find('h6', class_='title').a.attrs['href'],
                    'image': v.find('img', class_='lazyload').attrs['src']
                }
                videos_data.append(video)
            print('start pool2')
            with ThreadPoolExecutor(max_workers=2) as executor:
                future = executor.map(self.get_video_detail, videos_data)

            for f in future:
                if f:
                    print('final:',f)

            last = soup.find_all('a', class_='page-link')[-1].get_text()[:2]
            if last != '最後':
                break
            page += 1
    def get_video_detail(self,video):
        resp = self.session.get(url=video['url'])
        if resp.status_code != 200:
            return {}
        html = resp.text
        soup = BeautifulSoup(html,'html.parser')
        try:
            models = soup.find_all('a', class_='model')
            video['star'] = [m.find_next().attrs['title'] for m in models]
        except:
            video['star'] = []
        try:
            hash_tags = soup.find('h5',class_='tags h6-md').find_all('a')
            video['hash_tag'] = [h.get_text() for h in hash_tags]
        except:
            video['hash_tag'] = []
        pat = "hlsUrl = '(.*?)';"
        realUrl = re.compile(pat,re.S).findall(html)
        if realUrl:
            video['realUrl'] = realUrl[0]
            return video
        return {}

    def run(self):
        print('start tags')
        try:
            categories = json.loads(self.redis.get('jable'))
        except Exception as e:
            self.get_categories_list()
            categories = json.loads(self.redis.get('jable'))
        with ThreadPoolExecutor(max_workers=2) as executor:
            future = executor.map(self.get_video_list, categories[:2])


def downloadVideo(url):
    headers = {

        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4919.0 Safari/537.36",

    }
    session = cloudscraper.create_scraper(
        browser={
            'browser': 'firefox',
            'platform': 'windows',
            'mobile': False
        }
    )
    html = session.get(url=url)
    if html.status_code !=200:
        return
    html = html.text
    pat = "hlsUrl = '(.*?)';"
    realUrl = re.compile(pat, re.S).findall(html)
    m3u8Url = realUrl[0]
    m3u8Content = requests.get(m3u8Url, headers=headers)
    if m3u8Content.status_code != 200:
        print('block')
        return None
    m3u8Content = m3u8Content.text
    if "#EXTM3U" not in m3u8Content:
        print('error1')
        return None
    file_line = m3u8Content.split("\n")
    time.sleep(1)
    key = ""
    ts_list = []

    for index, line in enumerate(file_line):
        if "#EXT-X-KEY" in line:
            # 有的网站提供的ts格式的视频是经过AES加密的，需要解密
            method_pos = line.find("METHOD")
            comma_pos = line.find(",")
            method = line[method_pos:comma_pos].split('=')[1]
            print("Decode Method：%s" % method)

            uri_pos = line.find("URI")
            quotation_mark_pos = line.rfind('"')
            key_path = line[uri_pos:quotation_mark_pos].split('"')[1]

            key_url = m3u8Url.rsplit("/", 1)[0] + "/" + key_path  # 拼出key解密密钥URL
            res = requests.get(key_url, headers=headers)
            key = res.content
            print('key_url=', key_url)
            print("key：%s" % key)

        if "EXTINF" in line:
            # 找ts文件名
            file_name = m3u8Url.rsplit("/", 1)[0] + "/" + file_line[index + 1]
            ts_list.append(file_name)

    if not ts_list:
        return
    print(ts_list)
    print(key)

    resp = requests.get(url=ts_list[0], headers=headers)
    if resp.status_code != 200:
        print('status error')
        return
    if not key:
        with open('demoTS.ts','wb') as f:
            f.write(resp.content)
    else:
        decoder = AES.new(key, AES.MODE_CBC, key)
        fileContent = decoder.decrypt(resp.content)
        with open('demoTS.ts','wb') as f:
            f.write(fileContent)


if __name__ == '__main__':
    # git test (bug1 OK)
    # js = JableSpider()
    # js.run()
    downloadVideo(url='https://jable.tv/videos/ssis-400/')


