### Fuseki server connection
1. cd C:\Users\user\fuseki\apache-jena-fuseki-6.0.0
2. .\fuseki-server
3. http://localhost:3030/#/ in a browser

### Fuseki running in Docker
1. Pull Fuseki
You can run this from any directory:

```powershell
docker pull stain/jena-fuseki
```

2. Run Fuseki For INFERRA
```powershell
docker run -d `
  --name inferra-fuseki `
  -p 3030:3030 `
  -e ADMIN_PASSWORD=admin `
  -e FUSEKI_DATASET_1=inferra `
  -e TDB=2 `
  -v inferra-fuseki-data:/fuseki `
  stain/jena-fuseki
```

3. Then open:

```text
http://localhost:3030/
```
4. Login:
```text
username: admin
password: admin
```
5. INFERRA endpoints would be:

| Purpose	| URL |
| ---------- | ----- |
| Fuseki UI	 | http://localhost:3030/ |
| Dataset base	| http://localhost:3030/inferra |
| SPARQL query	| http://localhost:3030/inferra/s=parql |
| SPARQL update	| http://localhost:3030/inferra/update |
| Graph Store	| http://localhost:3030/inferra/data |


#### Useful Commands
| Task | 	Command |
| ----- | ----------- | 
| Check running containers	| docker ps |
| View  logs	| docker logs inferra-fuseki |
| Stop Fuseki	| docker stop inferra-fuseki |
| Start again	| docker start inferra-fuseki |
| Delete container	| docker rm -f inferra-fuseki |
| Delete persisted data	| docker volume rm inferra-fuseki-data |

If the name already exists, run:
```powershell
docker rm -f inferra-fuseki
then run the docker run command again.
``` 

