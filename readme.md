# strava-board

## Deployment

To deploy the Strava Board application, follow these steps:
1. Fetch the latest version of the Docker Compose file:
   ```bash
   curl -o docker-compose.yml https://raw.githubusercontent.com/skvortsovden/strava-board/main/docker-compose.yml
   ```
2. Start the application using Docker Compose:
   ```bash
   docker-compose up -d
   ```

## Strava limitations

### Error 403: Limit of connected athletes exceeded

Strava API has a limitation on the number of athletes that can be connected to an application. If you encounter the error "403: Limit of connected athletes exceeded," it means that your application has reached this limit. To resolve this issue, you may need to disconnect some athletes from your application or request an increase in your application's limits from Strava.