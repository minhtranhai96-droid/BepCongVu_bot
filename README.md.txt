Bep Cong Vu Bot

Deploy steps:
1) Upload repo to GitHub
2) Deploy to Render → Web Service
3) Add environment variable:
   BOT_TOKEN = <your_token>
4) After deploy, run:

https://api.telegram.org/bot<token>/setWebhook?url=<render_url>/<token>
