# Subir Este Proyecto a GitHub

## 1. Inicializar Git si aun no existe

```bash
cd /home/isa/Documents/Luis/jetson_fanet_live_stack
git init
git symbolic-ref HEAD refs/heads/main
```

## 2. Revisar que se versiona

```bash
git status
```

## 3. Crear el primer commit

```bash
git add .
git commit -m "Add Jetson live stack for ZED, Hikmicro and FANet"
```

## 4. Crear un repo vacio en GitHub

Hazlo desde la web de GitHub, por ejemplo con nombre:

- `jetson-fanet-live-stack`

No anadas `README`, `.gitignore` ni licencia desde GitHub si ya existen aqui.

## 5. Conectar el remoto y subir

```bash
git remote add origin <TU_URL_GITHUB>
git push -u origin main
```

Ejemplo:

```bash
git remote add origin git@github.com:usuario/jetson-fanet-live-stack.git
git push -u origin main
```

## Nota

En la version unificada actual, el repo principal recomendado ya es:

```bash
cd /home/isa/Documents/Luis/himikro_termical/termical_himikro_ros2
```

La carpeta `jetson_fanet_live_stack/` queda como subdirectorio interno del mismo repo.