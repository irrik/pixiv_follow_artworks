from selenium import webdriver
import os
import json
import requests
from requests.cookies import RequestsCookieJar

# user data 目录
pro_dir = r'C:\Users\18217\AppData\Local\Google\Chrome\User Data' # 输入你自己的目录

def get_cookie():
    '''
    获取本地cookies
    '''
    # 添加配置
    chrome_options = webdriver.ChromeOptions()
    # 静默模式
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--start-maximized')
    # 添加user data目录
    chrome_options.add_argument('user-data-dir='+os.path.abspath(pro_dir))
    driver = webdriver.Chrome(r'D:\chromedriver\chromedriver.exe', chrome_options=chrome_options) # 请输入你自己的chromedriver目录
    # 访问后,获取cookies
    driver.get('https://www.pixiv.net/')
    cookies = driver.get_cookies()
    # 保存cookies
    with open("pixiv_cookies.txt", "w") as fp:
        json.dump(cookies, fp)
    driver.close()
if __name__ == '__main__':
    proxy = {
            'http' : '127.0.0.1:1080',
            'https' : '127.0.0.1:1080'
    }
    get_cookie()