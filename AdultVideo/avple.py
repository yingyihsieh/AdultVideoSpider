import re
import time
import json
import random

import cloudscraper
import requests
from redis import Redis
from adultVideo.config import *
from bs4 import BeautifulSoup
from concurrent.futures.thread import ThreadPoolExecutor


class AvpleSpider():
    def __init__(self):
        self.redis = Redis.from_url(REDIS_ROUTE['tags'],decode_responses=True)
        self.headers = HEADERS
        self.base_url = 'https://avple.tv/'
        self.category_url = TAG_URL['avple']
        self.session = cloudscraper.create_scraper(
            browser={
                'browser': 'firefox',
                'platform': 'windows',
                'mobile': False
            }
        )

    def get_categories_list(self):
        with open(self.category_url,'r',encoding='utf-8') as f:
            data = json.loads(f.read())
        res = [{
            'tags': d['title'],
            'href': d['link']
        } for d in data]
        print(res)
        with open(self.category_url,'w',encoding='utf-8') as f:
            data = f.write(json.dumps(res,indent=4,ensure_ascii=False))
        self.redis.set('avple', json.dumps(res))

    def get_video_list(self,tag):
        baseUrl = tag['href'].rsplit('/', 2)[0]
        print(baseUrl)
        page = 1
        while page < 3:
            url = baseUrl + f'/{page}/date'
            print(url)
            resp = self.session.get(url=url)
            if resp.status_code != 200:
                break
            html = resp.text
            soup = BeautifulSoup(resp.text, 'html.parser')
            try:
                soup.find('h4',
                          class_='MuiTypography-root jss15 MuiTypography-h4 MuiTypography-colorPrimary MuiTypography-gutterBottom').get_text()
                break
            except:
                pass
            pat = '"createdAt".*?"img_preview":"(.*?)".*?"title":"(.*?)"'
            images = re.compile(pat, re.S).findall(html)
            if not images:
                break
            img = {}
            for i in images:
                img[i[1]] = i[0]
            videos = soup.find_all('div', class_='MuiGrid-root MuiGrid-item MuiGrid-grid-xs-6 MuiGrid-grid-sm-3')
            videos_data = []
            for v in videos:
                try:
                    data = {
                        'url': 'https://avple.tv' + v.find('a',
                                                            class_='MuiTypography-root MuiLink-root MuiLink-underlineNone MuiTypography-colorPrimary').attrs[
                            'href'],
                        'title': v.find('div', class_='MuiGridListTile-root').next_sibling.get_text(),
                        'mp4Url':'',
                        'hlsUrl':'',
                        'star':[],
                        'hash_tag':[]
                    }
                    data['image'] = img[data['title']]
                    videos_data.append(data)
                except:
                    continue

            with ThreadPoolExecutor(max_workers=2) as executor:
                future = executor.map(self.get_video_detail,videos_data)
            for f in future:
                if f:
                    print('final:',f)
            page += 1
            time.sleep(1.5)

    def get_video_detail(self,video):
        resp = self.session.get(url=video['url'])
        if resp.status_code != 200:
            return {}
        html = resp.content
        pat = '<div class="MuiBox-root jss21 jss15">(.*?)</div>'.encode()
        m3u8_pat = '"play":"(.*?)"'.encode()
        page_tag = re.compile(pat, re.S).findall(html)
        if not page_tag:
            return {}
        tag = page_tag[0].decode()
        hls = re.compile(m3u8_pat, re.S).findall(html)
        if not hls:
            return {}

        hls = self.cdn_choice(tag, hls[0].decode())
        video['hlsUrl'] = hls

        pat = '<span class="MuiChip-label">(.*?)<'.encode()
        hash_tags = re.compile(pat, re.S).findall(html)
        if hash_tags:
            hash_tags = [i.decode() for i in hash_tags]
            video['hash_tag'] = hash_tags
        else:
            video['hash_tag'] = []
        return video
        # base_url, file = req_m3u8(hls)
        # key, file, filePath, base_url = m3u8_parse(base_url, file)
        # if not file:
        #     return
        # ts_list = make_file_txt(base_url, filePath)
        # print(ts_list)
        # time.sleep(0.1)
        # download(key, ts_list, filePath)

    def cdn_choice(self, tag, hls):
        if tag in CHECK_JP_LIST:
            return f'https://{random.choice(CDN_MAP["jp"])}/file/avple-images/{hls}'
        if tag in CHECK_MD_LIST:
            return f'https://{random.choice(CDN_MAP["md"])}/file/avple-images/{hls}'
        if tag == '國產自拍':
            if 'https' in hls:
                return hls
            return f'https://{random.choice(CDN_MAP["home"])}/file/avple-images/{hls}'
        if tag == 'HongKongDoll':
            return hls
        return f'https://{random.choice(CDN_MAP["other"])}/file/avple-images/{hls}'

    def run(self):
        print('start tags')
        try:
            categories = json.loads(self.redis.get('avple'))
        except Exception as e:
            self.get_categories_list()
            categories = json.loads(self.redis.get('avple'))
        print(categories)
        with ThreadPoolExecutor(max_workers=2) as executor:
            future = executor.map(self.get_video_list, categories[:2])


def demo(url):
    session = cloudscraper.create_scraper(
        browser={
            'browser': 'firefox',
            'platform': 'windows',
            'mobile': False
        }
    )
    resp = session.get(url=url)
    if resp.status_code != 200:
        return {}
    html = resp.content
    pat = '<span class="MuiChip-label">(.*?)<'.encode()
    hash_tags = re.compile(pat, re.S).findall(html)
    hash_tags = [i.decode() for i in hash_tags]
    print(hash_tags)
if __name__ == '__main__':
    # git dev 1 100%
    # git demo2
    # git demo1
    avs = AvpleSpider()
    avs.run()
