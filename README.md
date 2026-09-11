# AquaFiordo (rubro: salmonicultura)

## Contexto del rubro
El salmon es una de las mayores exportaciones de Chile, que es el segundo productor mundial despues de Noruega.
Se cultiva en el mar del sur del pais, en centros con jaulas donde los peces pasan de smolt a tamano de cosecha
en un ciclo largo. Es un negocio biologico y de costos: se compra alimento (el mayor costo, con diferencia) y se
espera que los peces crezcan sanos, y el resultado depende de cuanto alimento se necesita por kilo de pez, de
cuantos peces se mueren en el camino y de cuanto rinde el pescado al pasarlo por la planta de proceso.

Tres rasgos definen al sector y explican por que los datos importan tanto:
- El alimento manda el costo, y el FCR lo resume. El FCR (factor de conversion alimenticia) es cuantos kilos de
  alimento se necesitan para ganar un kilo de pez. Un FCR de 1,2 es bueno; uno de 1,6 quiere decir que se gasto
  mucho mas alimento para el mismo crecimiento, y eso pega directo en el costo por kilo.
- La sanidad es el gran riesgo. Enfermedades como el SRS o parasitos como el caligus pueden disparar la mortalidad
  en un centro, matando biomasa que ya se alimento (plata perdida) y empeorando todos los indicadores de ese
  centro por meses.
- Del kilo vivo al kilo producto se pierde una parte. Al cosechar y procesar, un pez de varios kilos vivos rinde
  menos en producto final (merma o rendimiento en planta), y ese porcentaje varia por centro y por calibre. Es una
  perdida que muchas veces no se mira con cuidado.

La pregunta de fondo ya no es "cuantos kilos producimos", sino "cuanto nos cuesta cada kilo y por que: es el
alimento, es la mortalidad, es la merma, y en que centro se nos esta yendo la plata".

## La empresa
AquaFiordo es una productora chilena de salmon de tamano mediano, con centros de cultivo en el sur (Los Lagos,
Aysen y Magallanes). Cada centro tiene varias jaulas, y en cada jaula vive un lote o generacion de peces (de una
especie, con su fecha de siembra y su cantidad de smolts). Todos los dias se registra cuanto se alimento, cuantos
peces murieron, cuanto pesan y cuanta biomasa hay. Al final del ciclo, cada lote se cosecha y se mide cuanto rindio
en planta.

Durante 2025 la gerencia de operaciones ve que el costo por kilo subio, pero no tiene claro por que ni donde. Se
sospecha que uno de los centros tuvo un problema sanitario fuerte, pero nadie ha cruzado todavia la operacion
diaria con los eventos de sanidad, los costos de alimento y las cosechas para ponerle numero. El directorio quiere
separar las causas (alimento, mortalidad, merma) y saber en que centro se concentra el problema. Ahi entran
ustedes, un equipo externo con acceso a los datos de la empresa para responder con evidencia.

## Conceptos clave del rubro
- Smolt: el salmon joven que se siembra en el mar para engorda. La generacion parte con una cantidad de smolts.
- Engorda: la etapa en el mar en que el pez crece hasta el tamano de cosecha.
- Biomasa: los kilos totales de pez vivo en una jaula (poblacion por peso promedio). Es un stock que fluye: sube
  con el crecimiento y baja con la mortalidad y la cosecha.
- Mortalidad: los peces que mueren. Se cuenta en numero y en kilos (la biomasa que se pierde).
- FCR (factor de conversion alimenticia): kilos de alimento por kilo de pez ganado. Mas bajo es mejor.
- SGR (tasa de crecimiento): que tan rapido crece el pez, muy ligada a la temperatura del agua.
- Merma o rendimiento en planta: del kilo vivo cosechado, que porcentaje queda como producto final. Varia por
  centro y por calibre.
- Calibre: el rango de peso del pez cosechado (por ejemplo 4 a 5 kg).
- Centro de cultivo: la instalacion en el mar con sus jaulas.
- Jaula: cada modulo donde vive un lote de peces.
- Lote o generacion: el grupo de peces sembrados juntos, que se sigue en el tiempo.
- Evento sanitario: un brote de enfermedad (SRS) o parasitos (caligus) que sube la mortalidad y requiere
  tratamiento.

## Preguntas que la gerencia busca entender
Son las mismas para los tres equipos que trabajan este caso:
1. El costo por kilo subio: cuanto de eso es por un centro puntual con problemas y cuanto es general?
2. En el centro con mas costo, la causa es la mortalidad (un evento sanitario) o un FCR peor (mas alimento por
   kilo ganado), o ambas? Se pueden separar?
3. Cuanto se pierde del kilo vivo al kilo producto (merma), y como cambia por centro y por calibre?
4. La temperatura del agua, explica la estacionalidad del crecimiento a lo largo del anio?

## Fuentes disponibles
La empresa entrega cuatro fuentes:
- `origen_acuicultura.sqlite`: la base de operaciones, con varias tablas relacionadas: operacion diaria, centros,
  zonas, jaulas, lotes (generaciones), especies y cosechas.
- `origen_costos_alimento.csv`: el precio del alimento por tipo y por mes, del area de Abastecimiento.
- `origen_eventos_sanitarios.json`: los eventos de sanidad (SRS, caligus) por centro, con la fecha, la mortalidad
  asociada y el tratamiento.
- La API del dolar observado, desde `https://mindicador.cl/api/dolar/2025`.
