# El proyecto YVY

**YVY** significa *tierra* en guaraní, lengua originaria que se habla en Misiones y la región. El nombre refleja la conexión del proyecto con el territorio y con la educación agropecuaria local.

## Qué es

YVY es un **sistema distribuido de monitoreo meteorológico** diseñado específicamente para los **Institutos de Educación Agropecuaria (IEA)** de la provincia de Misiones, Argentina.

Cada IEA tiene una **estación meteorológica local** (sensor WH1081 + PC servidor con YVY) que recolecta datos de forma autónoma y los **sincroniza con un servidor central** cuando hay internet.

## Para qué sirve

- **Pedagógico**: los alumnos aprenden a observar, registrar y analizar datos meteorológicos reales de su propia institución.
- **Productivo**: los profesores y técnicos tienen información meteorológica precisa para clases prácticas y decisiones agropecuarias.
- **Investigación**: la red de IEAs genera un dataset de variables meteorológicas regionales útil para estudios académicos.

## Quiénes lo desarrollan

- **Estudiante a cargo del desarrollo**: Gonzalo (último año de Tecnicatura en Ciencia de Datos e Inteligencia Artificial, Posadas).
- **Marco institucional**: pasantía supervisada por **INET** (Instituto Nacional de Educación Tecnológica) y el **Ministerio de Educación**.
- **Beneficiarios directos**: los IEA de la provincia de Misiones.

## Diseño técnico

- **Offline-first**: funciona sin internet por días o semanas.
- **Modular evolutivo**: arquitectura DDD/Hexagonal, planeado para escalar de SQLite a PostgreSQL y de batch a streaming según crezca.
- **Open source y replicable**: la idea es que otras provincias o países puedan adoptar el sistema con mínimas adaptaciones regionales.

## Versión actual

Sistema en **fase de desarrollo activo**. Esta instalación es parte del proceso de validación previo al piloto.

---

*Página informativa — datos institucionales sujetos a actualización.*
