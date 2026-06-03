# Exécution VS Code

## Option recommandée

Terminal 1 :
```bash
docker compose up --build
```

Terminal 2 :
```bash
cd apps/mobile
npm install
npm run start
```

Scanner avec Expo Go.

## API rapide

- `GET http://localhost:3000/api/v1/stations`
- `GET http://localhost:3000/api/v1/parkings`
- `GET http://localhost:3000/api/v1/dashboard/kpi`
- `POST http://localhost:3000/api/v1/journey`
- `GET http://localhost:8000/docs`

## Note UX

L'app est volontairement simple : gros boutons, recommandations directes, textes courts, contraste élevé. Elle convient mieux aux clients de tous âges qu'une interface trop chargée.
