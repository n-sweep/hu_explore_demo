import pandas as pd


def main():

    keys = pd.read_csv('./data/explorer_demo_accessKeys.csv')
    # keys = pd.read_csv('./data/explorer_demo_accessKeys_inside.csv')

    keys = {
        "AWS_ACCESS_KEY_ID": keys['Access key ID'][0],
        "AWS_SECRET_ACCESS_KEY": keys['Secret access key'][0],
        "AWS_DEFAULT_REGION": 'us-east-1'
    }

    with open('./.env', 'r+') as f:
        vars = {(l:=line.split('='))[0]: l[1] for line in f.readlines()}
        vars.update(keys)
        f.writelines([f'{k}={v}' for k, v in vars.items()])


if __name__ == '__main__':
    main()
