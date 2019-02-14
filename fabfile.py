# /usr/bin/env python
# -*- coding: utf-8 -*-

from fabric.api import *
from fabric.colors import *
from fabric.contrib.files import exists
from fabric.contrib.console import prompt
import readline
import sys, os
import yaml
import time
import logging
from logging.handlers import TimedRotatingFileHandler as _TimedRotatingFileHandler
BASE_DIR = os.path.dirname(os.path.abspath(__file__))



#日志器
mylogger = logging.getLogger('logger1')
mylogger.setLevel(logging.INFO)
myhandler = _TimedRotatingFileHandler('{}/logs/all.log'.format(BASE_DIR), when='D', backupCount=7)
myhandler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - [line:%(lineno)d] - %(message)s'))
mylogger.addHandler(myhandler)


#初始化nginx的配置并写入到本地yaml文件
class _Nginx_init(object):
    Nginx_command = '/usr/local/nginx/sbin/nginx'
    remote_conf = '/usr/local/nginx/conf'
    def __init__(self, vip_host, real_ip, exclude_opts, info):
        self.vip_host = vip_host
        self.real_ip = real_ip.split(',')
        self.exclude_opts = exclude_opts
        self.info = info
        self.local_conf = os.path.join(BASE_DIR, 'local_rsync/CONF/%s') % self.vip_host
    def write_to_yaml(self):
        #备份yaml文件
        local('cp {}/conf/test.yml {}/conf/test.yml_bak_`date +%Y%m%d_%H%M%S`'.format(BASE_DIR, BASE_DIR))
        #生成新初始化的dict
        new_nd = {'real_ip': self.real_ip, 'exclude_opts': self.exclude_opts, 'info': self.info,'nginx_command': self.Nginx_command, 'conf': {'local_conf': self.local_conf, 'remote_conf': self.remote_conf}}
        #加载yaml原有配置，并加入新配置
        if os.path.getsize('{}/conf/test.yml'.format(BASE_DIR)) != 0:
            with open('{}/conf/test.yml'.format(BASE_DIR), 'r') as nyaml:
                my_yml = yaml.load(nyaml)
                my_yml[self.vip_host] = new_nd
            with open('{}/conf/test.yml'.format(BASE_DIR), 'w') as nyaml2:
                yaml.dump(my_yml, nyaml2)
        else:
            with open('{}/conf/test.yml'.format(BASE_DIR), 'w') as nyaml:
                my_yml = {}
                my_yml[self.vip_host] = new_nd
                yaml.dump(my_yml, nyaml)

def _confirm_init():
    while True:
        c = input(green('是否要初始化新nginx文件(Yy|Nn)：'))
        if c == 'Y' or c == 'y':
            print(green('##########初始化Nginx配置并写入本地yaml文件##########'))
            vip_host = input(green('请输入vip_host(eg：WTT_100_45)：'))
            real_ip = input(green('请输入nginx真实ip(以,为分隔符)：'))
            exclude_opts = input(green('请输入排除同步的目录(以,为分隔符)：'))
            info = input(green('请输入备注信息：'))
            #####
            New_nginx = _Nginx_init(vip_host, real_ip, exclude_opts, info)
            New_nginx.write_to_yaml()
            break
        elif c == 'N' or c == 'n':
            print(yellow('取消本次操作.'))
            sys.exit(0)
        else:
            print(red('输入错误，请重新输入!'))
            continue


#加载出yaml文件并获取到所需变量
with open('{}/conf/test.yml'.format(BASE_DIR), 'r') as all_conf:
    try:
        aconf = yaml.load(all_conf)
        rsync_server = aconf['rsync_server']
        ssh_user = aconf['ssh_user']
        ssh_port = aconf['ssh_port']
        ssh_key = aconf['ssh_key']
        ssh_pass = aconf['ssh_pass']
    except Exception as e:
        print(red('加载yaml文件错误!!!'), e)
        sys.exit(0)


@runs_once
def _select():
    '''选择同步的nginx主机'''
    VIP_host = []
    for i in aconf.keys():
        if i.isupper():
            VIP_host.append(i)
    sorted(VIP_host)
    
    print(white('当前本地环境所有纳入同步的Nginx服务器：'))
    for v in VIP_host:
        print(cyan(v) + '   --->   ' + cyan(aconf[v]['info']))
    prompt(green('选择要同步的Nginx服务器：'), key='nginx_vip')
    env.nginx_vip = env.nginx_vip.strip()


@runs_once
def _env_prepare():
    '''设置env,使用tomcat密钥登录处理'''
    #选择升级哪台主机或全部升级
    choose_list = []
    while True:
        hosts = aconf[env.nginx_vip]['real_ip']
        for r in range(0,len(hosts)):
            print(magenta('\t[%s]: %s') % (str(r), hosts[r]))
        print(magenta('\t[ALL]: 选择所有主机'))
        choose = input('选择要操作的选项：')
        
        if choose == 'ALL' or choose == 'all':
            choose_list = hosts
            break
        elif choose == '0' or choose == '1':
            choose_list.append(aconf[env.nginx_vip]['real_ip'][int(choose)])
            break
        else:
            print(red('输入错误，请重新输入!'))

    env.hosts = choose_list
    for ip in env.hosts:
        env.passwords[aconf['ssh_user'] + '@' + ip + ':' + str(aconf['ssh_port'])] = ''
    env.key_filename = ['{}/conf/server.key'.format(BASE_DIR)]
    #print(env.hosts, env.passwords, env.key_filename)
    return env


def _backup_conf():
    '''检查目录及备份'''
    if not exists('/opt/backup/{}'.format(env.nginx_vip)):
        print(yellow('备份目录不存在，新建备份目录.'))
        run('mkdir -p /opt/backup/{}'.format(env.nginx_vip))
    else:
        pass
    try:
        with cd('/opt/backup/{}'.format(env.nginx_vip)):
            print(green('清理10天前的备份'))
            run("find .  -maxdepth 1 -type d -mtime +10 -print -exec rm -rf '{}' \; ")
            print(green('备份conf目录到/opt/backup/{}'.format(env.nginx_vip)))
            run('rsync -aqcz {}/ {}_conf_{}'.format(aconf[env.nginx_vip]['conf']['remote_conf'], env.nginx_vip, '`date +%Y%m%d_%H%M%S`'))
    except Exception as e:
        print(red('备份出错，退出'), e)
        sys.exit(0) 


def _update_conf():
    '''同步配置'''
    exclude_opts = '{' + aconf[env.nginx_vip]['exclude_opts'] + '} '
    try:
        with cd(aconf[env.nginx_vip]['conf']['remote_conf']):
            run('rsync -aqcz --delete --exclude=' + exclude_opts + aconf['rsync_server'] + '/nginx/' + env.nginx_vip + '/ .')
    except Exception as e:
        print(red('rsync过程出错,请检查!'), e)
        sys.exit(0)


def _reload_service():
    '''使用-t检测nginx语法，通过则reload'''
    check_command = aconf[env.nginx_vip]['nginx_command'] + ' -t'
    reload_command = aconf[env.nginx_vip]['nginx_command'] + ' -sreload'
    with settings(warn_only=True):
        syntax_check = run(check_command)
        if syntax_check.failed:
            print(red('语法检测错误，请检查配置文件!'))
            sys.exit(0)
        else:
            p = run('ps -ef |grep nginx |grep -v grep |wc -l')
            if p == '0':
                print(yellow('语法检测成功，但nginx服务未启动，启动服务...'))
                run('set -m;' + aconf[env.nginx_vip]['nginx_command'])
            else:
                print(green('语法检测成功,reload服务.'))
                run('set -m;' + reload_command)

@runs_once
def _choose_rollback_dir():
    try:
        with hide('running', 'stdout', 'stderr'):
            rollback_menu = run('ls -t /opt/backup/{} | tac'.format(env.nginx_vip))
        print(white('远程服务器所有备份目录：'))
        for r in rollback_menu.split():
            print(cyan(r))
        prompt(yellow('请输入要回滚的备份：'), key='backupname')
    except Exception as e:
        print(red('备份目录不存在或有异常，请检查!'), e)
        sys.exit(0)


def _rollback():
    try:
        with cd(aconf[env.nginx_vip]['conf']['remote_conf']):
            run('rsync -aqzci --exclude=.git --exclude=.svn --exclude=logs --delete /opt/backup/{}/{}/ .'.format(env.nginx_vip, env.backupname))
    except Exception as e:
        print('备份失败，请检查备份目录或手动到服务器备份，本次选择的回滚主机为：{}'.format(env.nginx_vip), e)
        sys.exit(0)


def update():
    '''更新Nginx配置文件'''
    execute(_select)
    execute(_env_prepare)
    execute(_backup_conf)
    execute(_update_conf)
    execute(_reload_service)
    mylogger.info('#升级完成，本次升级工程为：{}，实际升级主机：{}'.format(env.nginx_vip, env.hosts))


def rollback():
    '''回滚配置'''
    execute(_select)
    execute(_env_prepare)
    execute(_choose_rollback_dir)
    execute(_rollback)
    execute(_reload_service)
    mylogger.info('#配置回滚，本次回滚工程为：{}，实际回滚主机：{}'.format(env.nginx_vip, env.hosts))


def _test(status='success'):
    print(status)


def test():
    '''测试服务器连通性'''
    execute(_test, 'fail')



if __name__ == '__main__':
    try:
        _confirm_init()
    except Exception as e:
        print(red('初始化失败，请检查!'), e)
