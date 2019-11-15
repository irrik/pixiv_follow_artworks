import requests
from requests.cookies import RequestsCookieJar
import json
import os
import time
import zipfile
import shutil
import imageio
from random import randint
from bs4 import BeautifulSoup

START_POS_FLAG = True

def restart_if_falied(func, max_tries, args=(), kwargs={}, secs=120, sleep=5):
    '''
    任务失败时重试，直到成功或者超过时间和次数
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
            if sleep is not None:
                time.sleep(sleep)
        else:
            break
    return res

def read_cookie():
    '''
    读取cookie,返回一个cookie对象
    '''
    jar = RequestsCookieJar()
    with open('pixiv_cookies.txt', 'r') as fp:
        cookies = json.load(fp)
        for cookie in cookies:
            jar.set(cookie['name'], cookie['value'])
    return jar

def get_page_num():
    '''
    请求收藏页面，返回收藏总页数
    '''
    headers = {
			'referer': 'https://www.pixiv.net/',
			'user-agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) '
				 'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36'
    }
    # 请求收藏页面，进行分析
    res = session.get(f'https://www.pixiv.net/bookmark.php?rest={REST}', headers=headers, timeout=1)
    res_bs = BeautifulSoup(res.text, 'html.parser')
    if res_bs.find('ul', attrs={'class': 'page-list'}) != None:
        page_num = int(res_bs.find('ul', attrs={'class': 'page-list'}).find_all('li')[-1].a.text)
    else:
        page_num = 1
    return page_num

def get_pic_information(page):
    '''
    获取所有收藏图片的url，构造图片的referer,图片的title, 图片的页数, 图片的类型,在一个tupe里返回6个list
    '''
    headers = {
			'referer': 'https://www.pixiv.net/',
			'user-agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) '
				 'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36'
    }
    pic_url_list = []
    pic_ref_list = []
    pic_title_list = []
    page_count_list = []
    pic_type_list = []
    pic_id_list = []

    url = f'https://www.pixiv.net/bookmark.php?rest={REST}&p={page}'
    res = session.get(url, headers=headers, timeout=1)
    res_bs = BeautifulSoup(res.text, 'html.parser')
    pic_div_list = res_bs.find('div', attrs={'class': 'display_editable_works'}).find_all('div', attrs={'class': '_layout-thumbnail'})
    pic_h1_list = res_bs.find('div', attrs={'class': 'display_editable_works'}).find_all('h1', attrs={'class': 'title'})
    li_list = res_bs.find('div', attrs={'class': 'display_editable_works'}).find_all('li', attrs={'class': 'image-item'})
    for item in li_list:
        if item.find('div', attrs={'class': 'page-count'}) != None:
            page_count = int(item.find('div', attrs={'class': 'page-count'}).span.text)
        else:
            page_count = 1
        page_count_list.append(page_count)
        pic_type_list.append(''.join(item.a['class'])) # 这里将class的值连在一起了。本来会被拆分，为了下面方便比较就这样写了
    for item in pic_div_list:
        pic_url = item.img.get('data-src').replace('c/150x150/', '')
        pic_ref = 'https://www.pixiv.net/artworks/' + item.img.get('data-id')
        pic_id_list.append(item.img.get('data-id'))
        pic_url_list.append(pic_url)
        pic_ref_list.append(pic_ref)
    for item in pic_h1_list:
        pic_title_list.append(item.text)
    print(f'已获取第{page}页链接，开始下载')
    return pic_url_list, pic_ref_list, pic_title_list, page_count_list, pic_type_list, pic_id_list

def download_pic(pic_url, pic_ref, pic_title, page_count, pic_type, pic_id):
    '''
    下载图片
    '''
    headers = {
			'referer': pic_ref,
			'user-agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) '
				 'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36'
    }
    os.makedirs(f'pixiv_{REST}_fav', exist_ok=True) # 图片存放目录
    table = str.maketrans('', '', r'\|/*?:"<>')
    pic_title = pic_title.translate(table) # 去除图片title中的非法字符
    if pic_type != 'work_workugoku-illust':
        if page_count == 1:
            while os.path.isfile(f'pixiv_{REST}_fav/' + pic_title + '.jpg'):
                pic_title += '-1'
            time.sleep(randint(5, 10)) # 暂停避免爬太快被封
            print('当前图片url: ', pic_url)
            r = session.get(pic_url, headers=headers, timeout=1)
            with open(f'pixiv_{REST}_fav/' + pic_title + '.jpg', 'wb') as fp:
                fp.write(r.content)
        else:
            try:
                pic_title_list = []
                for i in range(page_count):
                    time.sleep(randint(5, 10)) # 暂停避免爬太快被封
                    target_title = pic_title + str(i)
                    while os.path.isfile(f'pixiv_{REST}_fav/' + target_title + '.jpg'):
                        target_title += '-1'
                    target_url = pic_url.replace('p0', f'p{i}') # 替换目标url
                    print('当前图片url: ', target_url)
                    r = session.get(target_url, headers=headers, timeout=1)
                    with open(f'pixiv_{REST}_fav/' + target_title + '.jpg', 'wb') as fp:
                        fp.write(r.content)
                    pic_title_list.append(target_title)
            except:
                for pic_title in pic_title_list:
                    os.remove(f'pixiv_{REST}_fav/' + pic_title + '.jpg')
                raise ValueError('pic download error')
    else:
        time.sleep(randint(5, 10)) # 暂停避免爬太快被封
        get_gif(pic_id, pic_ref, pic_title)


def get_gif(pic_id, pic_ref, pic_title):
    '''
    获取收藏中的动图，由于pixiv采用静态图片放映方式，这里只能
    用请求原图zip再自己合成一个gif的方式获取
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
    headers['referer'] = pic_ref
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
    while os.path.isfile(f'pixiv_{REST}_fav/' + pic_title + '.gif'):
        pic_title += '-1'
    imageio.mimsave(f'pixiv_{REST}_fav/' + pic_title + '.gif', frame_list, 'GIF', duration=delay / 1000)

    for file_name in file_name_list:
        os.remove(file_name)
    os.remove('temp.zip')

def download():
    '''
    获取信息传递给下载函数下载图片
    '''
    try:
        page_num = get_page_num()
    except:
        page_num = restart_if_falied(get_page_num, 20)
    for page in range(START_PAGE, page_num + 1):
        setup_page(page)
        start_pos = get_pos()
        try:
            pic_url_list, pic_ref_list, pic_title_list, page_count_list, pic_type_list, pic_id_list = get_pic_information(page)
        except:
            pic_url_list, pic_ref_list, pic_title_list, page_count_list, pic_type_list, pic_id_list = restart_if_falied(get_pic_information, 20, (page,))
        for i in range(start_pos,len(pic_title_list)):
            try:
                download_pic(pic_url_list[i], pic_ref_list[i], pic_title_list[i], page_count_list[i], pic_type_list[i], pic_id_list[i])
                setup_pos(i)
            except:
                restart_if_falied(download_pic, 20, (pic_url_list[i], pic_ref_list[i], pic_title_list[i], page_count_list[i], pic_type_list[i], pic_id_list[i]))
        print(f'第{page}页任务完成')
    print('全部任务完成')
    clear_page()
    clear_pos()

def setup_page(page):
    '''
    记录当前下载的页数，以便任务中断再启动时继续任务
    '''
    with open(f'pixiv_{REST}_fav.txt', 'w') as fp:
        fp.write(str(page))

def check_page():
    '''
    程序启动时检查程序是否有中断，如果有，让用户选择任务开始方式
    '''
    if os.path.isfile(f'pixiv_{REST}_fav.txt'):
        choose_num = int(input('发现未完成任务，继续任务输入1，重新开始输入2：'))
        if choose_num == 1:
            with open(f'pixiv_{REST}_fav.txt', 'r') as fp:
                return int(fp.readline())
    os.makedirs(f'pixiv_{REST}_fav', exist_ok=True)
    shutil.rmtree(f'pixiv_{REST}_fav')
    return 1

def clear_page():
    '''
    任务完成后删除记录page的文件
    '''
    os.remove(f'pixiv_{REST}_fav.txt')

def setup_pos(pos):
    '''
    记录当前下载的链接位置
    '''
    with open(f'pixiv_{REST}_pos.txt', 'w') as fp:
        fp.write(str(pos + 1))

def get_pos():
    '''
    获取下载链接的位置
    '''
    global START_POS_FLAG
    if START_POS_FLAG:
        START_POS_FLAG = False
        if os.path.isfile(f'pixiv_{REST}_pos.txt'):
            with open(f'pixiv_{REST}_pos.txt', 'r') as fp:
                return int(fp.readline())
        return 0
    else:
        return 0

def clear_pos():
    '''
    完成任务后删除txt文件
    '''
    if os.path.isfile(f'pixiv_{REST}_pos.txt'):
        os.remove(f'pixiv_{REST}_pos.txt')
        


if __name__ == '__main__':
    session = requests.Session()
    proxies = {
            'http': '127.0.0.1:1080',
            'https': '127.0.0.1:1080'
    }
    session.proxies = proxies
    cookies = read_cookie()
    session.cookies = cookies
    # get_pic_information()
    choose_num = int(input('抓取公开收藏输入1，抓取私人收藏输入2: '))
    REST = 'show' if choose_num == 1 else 'hide'
    START_PAGE = check_page()
    download()
    