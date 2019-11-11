from selenium import webdriver
import os
import json
import requests
from requests.cookies import RequestsCookieJar
from bs4 import BeautifulSoup
from pprint import pprint
import time
from random import randint

TRAN_TABLE = str.maketrans('', '', r'/\*:?|<>"') # 替换非法字符的表

def get_url(url, headers=0):
	'''
	请求一个url，返回内容。之所以用这个函数是为了配合出错后重试的函数使用。因为默认的requests最大重试次数不够用
	'''
	if headers != 0:
		res = session.get(url, headers=headers)
	else:
		res = session.get(url)
	return res

def restart_if_failed(func, max_tries, args=(), kwargs={}, secs=120, sleep=5):
	'''
	当出错时重新运行某个函数,直到在超出时间或者达到最大重试次数
	'''
	import traceback
	from collections import deque
	
	dq = deque(maxlen=max_tries)
	while True:
		dq.append(time.time())
		try:
			func(*args, **kwargs)
		except:
			traceback.print_exc()
			if len(dq) == max_tries and time.time() - dq[0] < secs:
				break
			if sleep is not None:
				time.sleep(sleep)
		else: # 不出错的时候执行这个else语句
			break

def read_cookie():
	'''
	读取cookies
	之所以将获取和读取cookies分开写
	主要是节省时间，一次获取保存以后直接读取即可
	'''
	jar = RequestsCookieJar()
	with open('pixiv_cookies.txt', 'r') as fp:
		cookies = json.load(fp)
		for cookie in cookies:
			jar.set(cookie['name'], cookie['value'])
	return jar
	
def get_artist():
	'''
	获取画师昵称和id，以dict形式返回
	'''
	L = {} # 空字典存画师信息
	headers = {
			'referer': 'https://accounts.pixiv.net/login',
			'origin': 'https://accounts.pixiv.net',
			'user-agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) '
				 'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36'}
	res = session.get('https://www.pixiv.net/bookmark.php?type=user&rest=show', headers=headers) # 获取指定类型画师信息
	res_bs = BeautifulSoup(res.text, 'html.parser') # 构造bs对象
	if res_bs.find('div', attrs={'class': '_pager-complex'}) != None:
		max_page = res_bs.find('div', attrs={'class': '_pager-complex'}).find_all('li')[-2].text # 获取最大页码数，最大页码是在倒数第二的li里
	else:
		max_page = 1
	for i in range(1, int(max_page) + 1): # 获取画师信息
		url = f'https://www.pixiv.net/bookmark.php?type=user&rest=show&p={i}' # 获取
		res = session.get(url, headers=headers)
		res_bs = BeautifulSoup(res.text, 'html.parser') # 构造bs对象
		artist_list = res_bs.find('section', id='search-result').find_all('div', attrs={'class': 'userdata'})
		for item in artist_list:
			L[item.a['data-user_name']] = item.a['data-user_id']
	print('已获取所有画师信息')
	return L # 返回画师信息

def get_ajax_url(artist_dict):
	L = []
	for k, v in artist_dict.items():
		L.append(f'https://www.pixiv.net/ajax/user/{v}/profile/all')
	return L # 返回ajax链接去获取画师作品
	
	
def download_picture(ajax_list, artist_dict):
	'''
	解析数据传给下载函数下载
	'''
	name_list = [] # 获取作者名字
	artist_id_list = [] # 获取作者id
	for k, v in artist_dict.items():
		name_list.append(k)
		artist_id_list.append(v)
	name_count = 0
	artist_id_count = 0
	
	
	for ajax_url in ajax_list: # 遍历每一个画师作品
		artist_name = name_list[name_count].translate(TRAN_TABLE) # 获取画师名字
		
		artist_id = artist_id_list[artist_id_count] # 获取画师id
		referer_url = 'https://www.pixiv.net/member.php?id=' + str(artist_id)
		# print(referer_url)
		headers = {
			'referer': referer_url,
			'user-agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) '
				 'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36'}
		try:
			ajax_html = get_url(ajax_url, headers=headers) # 获取作品url,返回的是json数据
		except:
			restart_if_failed(get_url, 20, (ajax_url, headers))
		print('拿到画家作品数据')
		temp_id_dict = json.loads(ajax_html.text) # 将json反序列为对象
		illusts_dict = temp_id_dict['body']['illusts']
		manga_dict = temp_id_dict['body']['manga']
		# 判断作者是否有漫画作品,有就合并到一块，没有就用illusts_dict
		if len(manga_dict) == 0:
			work_dict = dict(illusts_dict)
		else:
			work_dict = dict(illusts_dict, **manga_dict)
		
		# 获取作品的id
		work_id_list = list(work_dict.keys())
		work_id_list.sort() # 对id从小到大排序
		work_id_list = work_id_list[::-1] # 让id从大到小排序
		# 每组图片48个
		limit_num = 48
		page_count = 0
		group_list = [work_id_list[i:i+limit_num] for i in range(0, len(work_id_list), limit_num)] # 分组，每个元素是一个list
		print('画师: ', artist_name, '作品', len(group_list), '页')
		for L in group_list:
			ids_big = 'https://www.pixiv.net/ajax/user/{}/profile/illusts?'.format(artist_id_list[artist_id_count])
			for id in L:
				ids = 'ids%5B%5D=' + id + '&'
				ids_big += ids
			work_url = ids_big + '&work_category=illust&is_first_page=' + str(page_count) # 构造请求图片的url
			print('第', page_count, '页')
			page_count += 1
			
			# 发起ajax请求去获取缩略图地址
			print(work_url)
			try:
				res = get_url(work_url)
			except:
				restart_if_failed(get_url, 20, (work_url,)) # 单个元素要传元组应该加上,
			res_dict = json.loads(res.text) # 反序列化为dict
			work_list = res_dict['body']['works'].values() # 获取作品信息，得到list,其中每个元素是一个dict
			for d in work_list:
				# 获取作品tile和缩略图url和页数
				title = d['title']
				pic_url = d['url']
				pic_id = d['illustId']
				page_count = d['pageCount']
				pic_url = pic_url.replace('c/250x250_80_a2/', '').replace('square1200', 'master1200')
				try:
					download_pic(title, pic_id, pic_url, artist_name, page_count) # 调用下载函数
				except:
					restart_if_failed(download_pic, 20, (title, pic_id, pic_url, artist_name, page_count)) # 下载失败的时候重试
		name_count += 1
		artist_id_count += 1
		print(artist_name, '完成')
	print('已完成所有任务')

def download_pic(title, pic_id, pic_url, artist_name, page_count):
	'''
	下载图片
	'''
	os.makedirs(artist_name, exist_ok=True) # 创建画师名字的文件夹

	referer_url = 'https://www.pixiv.net/artworks/' + str(pic_id)
	# 构造一下header头
	headers = {
		'referer': referer_url,
		'user-agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) '
			 'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36'}
	title = title.translate(TRAN_TABLE)
	if page_count == 1:
		time.sleep(randint(5,10)) # 暂停一下避免速度过快被封禁
		print('当前图片url: ', pic_url)
		r = session.get(pic_url, headers=headers) # 获取图片
		# 递归检查图片是否已经存在
		while os.path.isfile(f'{artist_name}/' + title + '.jpg'):
			title = title + '-1'
		with open(f'{artist_name}/' + title + '.jpg', 'wb') as fp:
			fp.write(r.content)
	else:
		for i in range(page_count):
			time.sleep(randint(5, 10)) # 暂停避免爬太快被封
			target_title = title + str(i)
			while os.path.isfile('pixiv_fav/' + target_title + '.jpg'):
				target_title += '-1'
			target_url = pic_url.replace('p0', f'p{i}') # 替换目标url
			print('当前图片url: ', target_url)
			r = session.get(target_url, headers=headers)
			with open(f'{artist_name}/' + target_title + '.jpg', 'wb') as fp:
				fp.write(r.content)

	

if __name__ == '__main__':
	proxy = {
			'http' : '127.0.0.1:1080',
			'https' : '127.0.0.1:1080'
	}
	session = requests.Session()	# 定义并配置session对象
	session.proxies = proxy
	cookies = read_cookie()
	session.cookies = cookies
	artist_dict = get_artist() # 获取画师name和id
	# pprint(artist_dict)
	ajax_list = get_ajax_url(artist_dict)
	# for i in ajax_list:
		# print(i)
	download_picture(ajax_list, artist_dict)