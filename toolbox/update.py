import os


def git_pull():
    os.system('pip install --upgrade pip')
    os.system('pip install --upgrade akshare')
    os.system('pip install --upgrade pywencai')

    os.system('git stash')

    r = -1
    while r != 0:
        r = os.system('git pull')
        print(r)

    os.system('git stash pop')


if __name__ == '__main__':
    git_pull()
