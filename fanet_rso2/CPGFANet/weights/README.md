# Pesos del modelo

Este directorio esta reservado para los pesos de inferencia de FANet.

El despliegue actual espera por defecto:

- `160.pth`

Importante:

- No se ha incluido aqui automaticamente porque pesa casi 1 GB y GitHub normal no lo admite bien sin Git LFS.
- Si quieres que este repo sea autoportable, usa una de estas dos opciones:
  - guardar `160.pth` aqui usando Git LFS
  - no versionarlo y copiarlo manualmente en esta carpeta en cada robot

Ruta esperada dentro del contenedor:

- `/workspace/CPGFANet/weights/160.pth`

Ruta esperada en el host con esta stack:

- `jetson_fanet_live_stack/../fanet_rso2/CPGFANet/weights/160.pth`

No hace falta reconstruir la imagen para actualizar o restaurar el peso.
`scripts/up.sh` monta esta carpeta del host dentro del contenedor automaticamente.