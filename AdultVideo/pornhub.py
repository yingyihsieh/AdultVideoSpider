import re
import time
import json
import random
import requests
from redis import StrictRedis
from adultVideo.config import *
from bs4 import BeautifulSoup
from concurrent.futures.thread import ThreadPoolExecutor

class PornHubSpider():
    def __init__(self):
        # if need proxy, add here
        self.headers = HEADERS
        self.base_url = 'https://cn.pornhub.com/'
        self.category_url = TAG_URL['pornhub']
        self.redis = StrictRedis.from_url(REDIS_ROUTE['tags'],decode_responses=True)
        redis2 = StrictRedis.from_url(REDIS_ROUTE['videos'],decode_responses=True)
        self.pipe = redis2.pipeline()
    def get_category_list(self):
        '''save all categories to db or file in one time'''
        print('crawl tags start')
        resp = requests.get(url=self.category_url, headers=self.headers)
        html = resp.text
        soup = BeautifulSoup(html, 'html.parser')
        # block = soup.find('ul', class_='nf-categories tracking')
        target = soup.find_all('li', class_='catPic')

        res = [{
            'href': self.base_url[:-1] + i.find('a', class_='js-mxp').attrs['href'],
            'tags': i.find('a', class_='js-mxp').attrs['alt'],
        } for i in target]

        self.redis.set('pornhub', json.dumps(res))
        print('save over')

    def video_spider(self,page_url):
        page_count = 1
        while page_count < 2:
            url = page_url + str(page_count)
            print('start crawl', url)
            resp = requests.get(url=url, headers=self.headers)
            if resp.status_code != 200:
                return None
            html = resp.text
            next = self.parse_video(html)
            if not next:
                return None

            with ThreadPoolExecutor(max_workers=2) as executor:
                future = executor.map(self.video_detail, next)
            for item in future:
                self.pipe.set(item['url'],json.dumps(item))
            self.pipe.execute()
            page_count += 1
            time.sleep(5)

    def parse_video(self, html):
        # parse video
        soup = BeautifulSoup(html, 'html.parser')
        block = soup.find_all('li', class_='pcVideoListItem js-pop videoblock videoBox')
        # add a func for saving to db
        result = []
        for i in block:
            video = {}
            video['image'] = i.find('img').attrs['data-thumb_url']
            video['title'] = i.find('span', class_='title').get_text().strip()
            video['url'] = self.base_url[:-1] + i.find('a').attrs['href']
            result.append(video)
        return result

    def rebuild(self, data):
        data = data.strip().split(';')
        print(data)
        res = {}
        for i in data:
            if not i:
                continue
            k, v = i.replace('var ', '').split('=', 1)
            if ' + ' in v:
                v = v.replace(' + ', '')
            res[k] = v.replace('"', '')
        return res

    # 需要先把注释掉的JS程式码拿掉
    def decrypt(self, data, dic):
        pat = '/\*.*?(\w+).*?\*/'
        fake_data = re.compile(pat, re.S).findall(data)
        data = data.strip().split('=', 1)[1][:-1]
        for f in fake_data:
            fake_part = f'/* + {f} + */'
            data = data.replace(fake_part, '')

        data = data.replace(' + ', '|').split('|')
        print(data)
        url = ''
        for i in data:
            if i:
                url += dic[i]
        return url

    def get_tags(self,html):
        soup = BeautifulSoup(html,'html.parser')
        try:
            tags = soup.find('div',class_='categoriesWrapper').find_all('a',class_='item')
            tags = [t.get_text() for t in tags]
        except:
            tags = []
        try:
            stars = soup.find('div',class_='pornstarsWrapper js-pornstarsWrapper').find_all('a',class_='pstar-list-btn js-mxp')
            stars = [t.get_text().strip() for t in stars]
        except:
            stars = []
        return tags, stars

    def video_detail(self, data):
        print('start decrypt',data)
        resp = requests.get(url=data['url'], headers=HEADERS)
        html = resp.text
        hash_tag,stars = self.get_tags(html)
        data['hash_tag'] = hash_tag
        data['stars'] = stars
        pat = "nextVideoObject.*?nextVideo.*?(var.*?)var.nextVideoPlaylistObject"
        first_part = re.compile(pat, re.S).findall(html)
        first_part = first_part[0].strip()
        pat = "flashvars.*?\d+.*?mediaDefinitions.*?media_\d\;"
        res_part = re.compile(pat, re.S).findall(first_part)
        for item in res_part:
            first_part = first_part.replace(item, '|')
        result = first_part.split('|')
        print('result:',result)
        for r in result[:-1]:
            if not r:
                continue
            pat = 'var media_\d.*'
            second_data = re.compile(pat, re.S).findall(r)
            if not second_data:
                continue
            second_data = second_data[0]
            first_data = r.replace(second_data, '')
            decode_map = self.rebuild(first_data)
            m3u8_url = self.decrypt(second_data, decode_map)
            if m3u8_url:
                data['realUrl'] = m3u8_url
                return data

    def run(self):
        try:
            categories = json.loads(self.redis.get('pornhub'))
        except Exception as e:
            self.get_category_list()
            categories = json.loads(self.redis.get('pornhub'))
        print(categories)

        # add coroutine or threading
        for tag in categories[57:58]:
            # classify different url format
            if '?' in tag['href']:
                url = tag['href'] + '&page='
            else:
                url = tag['href'] + '?page='
            self.video_spider(url)

if __name__ == '__main__':
    ps = PornHubSpider()
    ps.run()
