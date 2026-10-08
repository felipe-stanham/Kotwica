```
# .deploy-secrets — NOT committed to git
# One section per target+environment combination

[homeserver.dev]
HOST=192.168.x.x
SSH_USER=deploy
SSH_KEY_PATH=~/.ssh/homeserver
DEPLOY_PATH=/opt/apps/myapp-dev
PORT=8081

[homeserver.prd]
HOST=192.168.x.x
SSH_USER=deploy
SSH_KEY_PATH=~/.ssh/homeserver
DEPLOY_PATH=/opt/apps/myapp
PORT=8080

[clientA.prd]
HOST=<ip>
SSH_USER=<user>
SSH_KEY_PATH=~/.ssh/clientA
DEPLOY_PATH=/opt/apps/myapp
PORT=8080
```