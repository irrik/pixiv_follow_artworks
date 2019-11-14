import requests
import json
import os
import zipfile
import time
from bs4 import BeautifulSoup
from urllib.parse import quote
from requests.cookies import RequestsCookieJar
from random import randint
import imageio

COLLECTION = 5000 # 图片下载阈值
TRAN_TABLE = str.maketrans('', '', r'/\*:?|<>"') # 替换非法字符的表

def read_cookies():
    '''
    从文件里读取cookies
    '''
    jar = RequestsCookieJar()
    with open('pixiv_cookies.txt', 'r') as fp:
        cookies = json.load(fp)
        for cookie in cookies:
            jar.set(cookie['name'], cookie['value'])
    return jar

def restart_if_failed(func, max_tries, args=(), kwargs={}, secs=120, sleep=5):
    '''
    当任务失败时重启目标函数, 直到任务成功或者在给定时间内达到最大重试次数
    '''
    import traceback
    from collections import deque
    dq = deque(maxlen=max_tries)
    while True:
        dq.append(time.time())
        try:
            res = func(*args, **kwargs)
        except:
            traceback.print_exc()
            if len(dq) == max_tries and time.time() - dq[0] < secs:
                break
            if sleep != None:
                time.sleep(sleep)
        else:
            break
    return res

def get_page_num():
    '''
    获取并返回搜索结果的总页数
    '''
    ref_url = 'https://www.pixiv.net/search.php?&word=' + TAG
    url = f'https://www.pixiv.net/ajax/search/artworks/{TAG}?word={TAG}'
    
    headers = {
            'referer': ref_url,
			'user-agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) '
				'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36'}
    res = session.get(url, headers=headers, timeout=1)
    res_obj = json.loads(res.text)
    page_num = res_obj['body']['illustManga']['total']
    print('已获取作品总页数')
    return page_num // 60

def get_pic_info(page):
    '''
    提取指定页码信息，整理后返回
    '''
    ref_url = f'https://www.pixiv.net/search.php?word={TAG}&p={page}'
    url = f'https://www.pixiv.net/ajax/search/artworks/{TAG}?word={TAG}&p={page}'
    headers = {
            'referer': ref_url,
			'user-agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) '
				'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36'}
    res = session.get(url, headers=headers, timeout=1)
    res_obj = json.loads(res.text)
    pic_id_list = []
    pic_illustType_list = []
    pic_pageCount_list = []
    pic_title_list = []
    pic_url_list = []
    for data in res_obj['body']['illustManga']['data']:
        pic_id_list.append(data['id'])
        pic_illustType_list.append(data['illustType'])
        pic_pageCount_list.append(data['pageCount'])
        pic_title_list.append(data['title'])
        pic_url_list.append(data['url'].replace('/c/250x250_80_a2','').replace('square', 'master'))
    print('获取当前url作品信息', url)
    return pic_id_list, pic_illustType_list, pic_pageCount_list, pic_title_list, pic_url_list


def get_collection_num(pic_id):
    '''
    获取图片的收藏数并返回
    '''
    url = f'https://www.pixiv.net/artworks/{pic_id}'
    headers = {
			'user-agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) '
				'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36'}
    print('检查作品收藏数:', url)
    res = session.get(url, headers=headers, timeout=1)
    res_html = BeautifulSoup(res.text, 'html.parser')
    return json.loads(res_html.find('meta', attrs={'id': 'meta-preload-data'})['content'])['illust'][f'{pic_id}']['bookmarkCount']

def download_pic(pic_title, pic_id, pic_url, pic_pageCount, pic_illustType):
    '''
    下载图片
    '''
    os.makedirs('high_collection', exist_ok=True) # 创建画师名字的文件夹
    referer_url = 'https://www.pixiv.net/artworks/' + str(pic_id)
    pic_title = pic_title.translate(TRAN_TABLE)
    if pic_illustType != 2:
        # 构造一下header头
        headers = {
            'referer': referer_url,
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36'}
        
        if pic_pageCount == 1:
            time.sleep(randint(5,10)) # 暂停一下避免速度过快被封禁
            print('当前图片url: ', pic_url)
            r = session.get(pic_url, headers=headers, timeout=1) # 获取图片
            # 递归检查图片是否已经存在
            while os.path.isfile('high_collection/' + pic_title + '.jpg'):
                pic_title += '-1'
            with open('high_collection/' + pic_title + '.jpg', 'wb') as fp:
                fp.write(r.content)
        else:
            try:
                pic_title_list = []
                for i in range(pic_pageCount):
                    time.sleep(randint(5, 10)) # 暂停避免爬太快被封
                    target_title = pic_title + str(i)
                    while os.path.isfile('high_collection/' + target_title + '.jpg'):
                        target_title += '-1'
                    target_url = pic_url.replace('p0', f'p{i}') # 替换目标url
                    print('当前图片url: ', target_url)
                    r = session.get(target_url, headers=headers, timeout=1)
                    with open('high_collection/' + target_title + '.jpg', 'wb') as fp:
                        fp.write(r.content)
                    pic_title_list.append(target_title)
            except:
                for pic_title in pic_title_list:
                    os.remove('high_collection/' + pic_title + '.jpg')
                raise ValueError('pic download error')
    else:
        time.sleep(randint(5, 10)) # 暂停避免爬太快被封
        get_gif(pic_title, pic_id, referer_url)

def get_gif(pic_title, pic_id, referer_url):
	'''
	处理动图的情况，下载图片压缩包，在本地合成动图
	'''
	file_name_list = []
	frame_list = []
	print('正在处理动图')
	url = f'https://www.pixiv.net/ajax/illust/{pic_id}/ugoira_meta'
	headers = {
			'user-agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) '
				'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36'}
	res = session.get(url, headers=headers, timeout=1)
	res_obj = json.loads(res.text)
	delay = res_obj['body']['frames'][0]['delay']
	originalSrc = res_obj['body']['originalSrc']
	headers['referer'] = referer_url
	res = session.get(originalSrc, headers=headers, timeout=1) # 请求原图的压缩包，返回的是静态图的zip文件，需要自己处理合成为gif
	with open('temp.zip', 'wb') as fp:
		fp.write(res.content)
	zip_obj = zipfile.ZipFile('temp.zip', 'r')
	for file_name in zip_obj.namelist():
		file_name_list.append(file_name)
		zip_obj.extract(file_name)
	zip_obj.close() # 关闭zip文件
	# 合成gif图片
	for file_name in file_name_list:
		frame_list.append(imageio.imread(file_name))
	while os.path.isfile('high_collection/' + pic_title + '.gif'):
		pic_title += '-1'
	imageio.mimsave('high_collection/' + pic_title + '.gif', frame_list, 'GIF', duration=delay / 1000)

	for file_name in file_name_list:
		os.remove(file_name)
	os.remove('temp.zip')

def download():
    '''
    根据收藏数判断是否下载作品
    '''
    try:
        page_num = get_page_num()
    except:
        page_num = restart_if_failed(get_page_num, 20)
    for page in range(1, page_num + 1):
        try:
            pic_id_list, pic_illustType_list, pic_pageCount_list, pic_title_list, pic_url_list = get_pic_info(page)
        except:
            pic_id_list, pic_illustType_list, pic_pageCount_list, pic_title_list, pic_url_list = restart_if_failed(get_pic_info, 20, (page,))
        for i in range(len(pic_id_list)):
            try:
                time.sleep(randint(1,3))
                collection = get_collection_num(pic_id_list[i])
            except:
                collection = restart_if_failed(get_collection_num, 20, (pic_id_list[i],))
            if collection > COLLECTION:
                print('发现高收藏作品:',pic_id_list[i])
                try:
                    download_pic(pic_title_list[i], pic_id_list[i], pic_url_list[i], pic_pageCount_list[i], pic_illustType_list[i])
                except:
                    restart_if_failed(download_pic, 20, (pic_title_list[i], pic_id_list[i], pic_url_list[i], pic_pageCount_list[i], pic_illustType_list[i]))

    



if __name__ == '__main__':
    proxies = {
        'http': '127.0.0.1:1080',
        'https': '127.0.0.1:1080'
    }
    session = requests.session()
    session.proxies = proxies
    cookies = read_cookies()
    session.cookies = cookies
    TAG = quote(input('请输入要搜索的tag:'))
    download()
