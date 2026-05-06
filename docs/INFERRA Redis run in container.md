## Open powershell and run:
```
docker run -d --name inferra-redis -p 6379:6379 redis:7
```

## Test Redis
```
docker exec -it inferra-redis redis-cli ping
```

## Your app can connect with
```
redis://localhost:6379/0
```

### Useful Commands
| Task	| Command                                       |
| ----- | -------------------- |
|Start Redis |	docker start inferra-redis |
|Stop Redis	| docker stop inferra-redis |
|Open Redis CLI |	docker exec -it inferra-redis redis-cli |
|Remove container |	docker rm -f inferra-redis |
|View logs |	docker logs inferra-redis |