# Command line tool for GO-E-MON

## How to install

Install goemon-cli with pip.
(confirmed to work with Python 3.9)

```
$ pip install git+https://github.com/goemon-cloud/goemon-cli
```

1. Log in to GO-E-MON http://goemon.cloud
2. Open User Preferences page https://goemon.cloud/settings
3. Create a Developer Token
4. Set the acquired token to an environment variable

```
$ export GOEMON_TOKEN=(Your token here)
```

## How to use

If the URL of your task is `https://goemon.cloud/t/YOUR-TASK-ID`, you can import and export it with the following command:

Import:
```
$ goemon import 8TdZSZOIOfWsqIpK7oQM --all
```

Export:
```
# Check mode: Just display the diff.
$ goemon export 8TdZSZOIOfWsqIpK7oQM --all --dry-run

$ goemon export 8TdZSZOIOfWsqIpK7oQM --all
```
