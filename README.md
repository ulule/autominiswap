# autominiswap

To deploy to heroku, create the app and set the buildpacks
```
heroku apps:create --region eu
heroku buildpacks:set heroku/go
heroku buildpacks:add heroku/python
```

The following config variables are required
```
heroku config:set LUCCA_ADDR=your-lucca-addr # something like https://mycompany.ilucca.net
heroku config:set LUCCA_LOGIN=your-lucca-login
heroku config:set LUCCA_PASSWORD=your-lucca-password
```

The following config variables are optional
```
heroku config:set LEGAL_ENTITY="FOO SAS" # keep only people from this lucca legal entity
heroku config:set SWAP_EXCLUSION="alice,bob" # comma-separated list of people name
heroku config:set SWAP_LUNCH_EXCLUSION="alice,bob"
```

Good luck! Do not hesitate to open issues.