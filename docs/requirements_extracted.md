Prueba Técnica

AI Products — Ingeniero/a de IA

Sistema Multi-Agente con Orquestación y Responsabilidades Claras

Zebra — AI Transformation Company

1. Sobre esta prueba

1.1 Contexto

En Zebra estamos construyendo productos de IA aplicada para clientes industriales, sector público y servicios B2B. Buscamos incorporar a nuestro equipo de Tecnología un/a Ingeniero/a de IA con capacidad para diseñar e implementar sistemas basados en agentes de IA, integrando LLMs, herramientas externas y lógica de orquestación.

Esta prueba técnica evalúa tu capacidad para diseñar un sistema multi-agente funcional. El foco de la evaluación está en cómo diseñas el sistema, no en la complejidad del caso de uso ni en que el resultado sea un producto terminado.

1.2 Qué evaluamos

Nos interesa entender cómo piensas y tomas decisiones técnicas. En concreto:

Criterio

Peso

Qué buscamos

Arquitectura del sistema de agentes

25%

Separación clara de responsabilidades, contratos de entrada/salida definidos, roles con límites explícitos.

Orquestación y control de flujo

25%

Lógica de coordinación explícita, gestión del estado compartido, manejo de dependencias entre agentes.

Resiliencia y manejo de errores

15%

Qué ocurre cuando un agente falla, devuelve datos incoherentes o tarda demasiado. Reintentos, fallbacks, validaciones.

Observabilidad

10%

Logs estructurados, trazas del flujo de ejecución, métricas básicas. Capacidad de depurar el sistema.

Calidad del código y documentación

10%

Código limpio, organizado y legible. README con instrucciones claras para arrancar el sistema.

Criterio técnico y trade-offs

10%

Capacidad de razonar y justificar decisiones. No buscamos la solución perfecta, sino que entiendas los compromisos.

Extras (bonus)

5%

Interfaz visual, Dockerfile, tests automatizados, diagramas de arquitectura, uso creativo de tools.

1.3 Plazos y dedicación estimada

Plazo de entrega: 7 días naturales desde la recepción de esta prueba.

Defensa técnica: tras la entrega, haremos una sesión de 30–45 minutos donde presentarás tu solución, explicarás las decisiones tomadas y discutiremos posibles mejoras. No es una presentación formal: es una conversación técnica que emplearemos también para conocernos mejor.

1.4 Stack tecnológico

Tienes libertad total de elección de lenguaje, framework y LLM. Dicho esto, ten en cuenta que en Zebra trabajamos principalmente con Python y modelos de OpenAI y Anthropic. No es obligatorio usar nuestro stack, pero si lo haces facilitará la revisión.

Si usas un LLM de pago, incluye instrucciones claras para configurar las API keys. No incluyas claves reales en el repositorio.

2. Problema a resolver

El sistema debe recibir una solicitud compleja de un usuario, descomponerla en subtareas, coordinar agentes especializados y generar una respuesta final estructurada y validada.

2.1 Ejemplo orientativo

«Quiero lanzar una plataforma SaaS de gestión de turnos para clínicas pequeñas en España. Necesito: análisis del problema y del usuario, propuesta de funcionalidades (MVP y fases posteriores), identificación de riesgos legales básicos, arquitectura técnica inicial y plan de ejecución de cuatro semanas.»

Este ejemplo es solo una referencia. Puedes cambiar el dominio del problema siempre que permita demostrar:

Descomposición del problema en subtareas con dependencias entre ellas

Coordinación real entre agentes con responsabilidades diferentes (no solo prompts distintos)

Generación de un resultado final coherente y trazable

2.2 Alcance esperado

No esperamos un producto terminado. Esperamos un flujo funcional de extremo a extremo que demuestre un diseño claro. En concreto:

Una solicitud de usuario entra al sistema y produce un resultado estructurado

Al menos 4 agentes participan con roles diferenciados

La orquestación es explícita y comprensible

Hay mecanismos básicos de validación y manejo de errores

Se puede entender la arquitectura sin necesidad de leer todo el código

3. Requisitos funcionales

3.1 Arquitectura multi-agente (obligatorio)

El sistema debe incluir al menos cuatro agentes con responsabilidades claramente diferenciadas. No se trata de usar prompts distintos con un mismo LLM, sino de definir roles con objetivos, límites y contratos de entrada/salida bien definidos.

Cada agente debe tener documentado:

Responsabilidad: qué hace y qué NO hace

Input: qué datos espera recibir (esquema o estructura)

Output: qué datos produce (esquema o estructura)

Condiciones de error: qué puede salir mal y cómo lo comunica

Agentes mínimos requeridos

La siguiente distribución es orientativa. Puedes renombrar, reorganizar o añadir agentes siempre que mantengas al menos cuatro con roles diferenciados.

Orchestrator / Manager Agent

Coordina el sistema completo. Decide qué agentes intervienen, en qué orden, gestiona el estado compartido, maneja dependencias entre resultados y consolida la respuesta final. Es el único punto de entrada y salida del sistema.

Domain Expert Agent

Analiza el problema planteado por el usuario. Comprende el dominio, identifica requisitos, restricciones y supuestos, y propone la estructura inicial del informe o solución. Su output alimenta al resto de agentes.

Technical Architect Agent

Propone la solución técnica. Diseña una arquitectura de alto nivel, identifica componentes clave, plantea decisiones técnicas con sus trade-offs y propone estrategias de datos, seguridad y despliegue. Recibe el contexto del Domain Expert como input.

Reviewer / Critic Agent

Revisa los resultados generados por los demás agentes. Detecta contradicciones, lagunas o incoherencias. Evalúa si las respuestas cumplen criterios de calidad mínimos. Puede solicitar revisiones al Orchestrator o aprobar el resultado final.

Agentes opcionales (bonus)

Legal / Risk Agent: identifica riesgos regulatorios o legales del dominio

Research Agent: amplía información relevante del contexto mediante búsqueda web o RAG

Planning Agent: genera planes de ejecución, roadmaps o cronogramas

3.2 Orquestación explícita (obligatorio)

La lógica de coordinación entre agentes debe ser explícita y comprensible. Debe quedar claro:

Cómo se decide qué agente actúa y en qué orden

Qué información comparte cada agente con los demás (estado compartido, mensajes, eventos)

Qué pasa cuando un agente falla, devuelve datos incompletos o tarda demasiado

Si hay ciclos de revisión (Reviewer → Orchestrator → Agente), cuántas iteraciones máximas se permiten y qué criterio de parada se usa

La orquestación puede implementarse con: estado compartido (state machine), paso de mensajes estructurados, enfoque event-driven, o grafos (e.g., LangGraph). Elige el patrón que mejor se adapte a tu diseño y justifícalo.

3.3 Uso de tools (opcional)

El uso de herramientas externas es opcional, pero si se utilizan deben tener sentido arquitectónico y su acceso debe estar limitado según el rol de cada agente. No todos los agentes necesitan acceso a todas las tools.

Ejemplos de herramientas que pueden aportar valor:

Almacenamiento del estado del sistema (en memoria, SQLite, Redis)

Validación de esquemas de datos (Pydantic, JSON Schema)

Mecanismos de scoring o evaluación de calidad de resultados

Sistema de logging estructurado o trazabilidad (e.g., LangSmith, OpenTelemetry)

Caché de respuestas para mejorar repetibilidad y reducir costes

Simulación de fallos para probar resiliencia

3.4 Output estructurado (obligatorio)

El sistema debe generar una respuesta final claramente estructurada (JSON o Markdown jerárquico). La respuesta debe incluir:

Resultado consolidado de la solicitud del usuario

Identificación del agente responsable de cada sección

Trazas básicas del proceso de decisión (qué agentes participaron, en qué orden, tiempos)

Revisiones o reintentos realizados (si los hubo)

Nivel de confianza de cada sección (puede ser un score numérico, semáforo, etc.)

Supuestos y limitaciones del análisis

4. Entregables

4.1 Obligatorios

Repositorio Git con el código fuente organizado. Puede ser un repositorio público en GitHub/GitLab o un archivo .zip con el histórico de commits.

README.md con: descripción del sistema, instrucciones de instalación y ejecución, dependencias necesarias, cómo configurar API keys (si aplica) y cómo lanzar una ejecución de ejemplo.

Scripts de inicialización y prueba que permitan arrancar el sistema y ejecutar al menos una solicitud completa de ejemplo.

4.2 Opcionales (valorados positivamente)

Diagramas de arquitectura (componentes, flujo de datos, secuencia)

Dockerfile o docker-compose para levantar el entorno completo

Interfaz sencilla (web o CLI) que permita visualizar el flujo y los resultados

Tests automatizados (unitarios o de integración)

Documento de decisiones técnicas (ADR o similar) explicando los trade-offs principales

4.3 Formato de entrega

Envía el enlace al repositorio (o el .zip) por email a la dirección que te hemos facilitado. Si el repositorio es privado, añade acceso de lectura al usuario que te indiquemos.

5. Qué NO buscamos

Para evitar que inviertas tiempo en la dirección equivocada:

Un producto terminado. Un flujo funcional con buen diseño es suficiente.

Complejidad artificial. No añadas agentes o herramientas solo por añadir. Cada componente debe tener una justificación.

Prompts sueltos sin orquestación. Cuatro llamadas secuenciales a un LLM con system prompts diferentes no es un sistema multi-agente.

Código sin documentar. Si no podemos arrancarlo o entender qué hace, no podemos evaluarlo.

Overengineering. Kubernetes, microservicios, event bus distribuido... Si no lo necesitas para resolver el problema, no lo añadas.

6. Resumen

Lo que priorizamos: arquitectura, claridad y criterio por encima del resultado final.

Plazo: 7 días naturales

Formato: repositorio Git (o .zip) con README, código fuente y scripts de ejecución.

Siguiente paso: defensa técnica de 30–45 minutos tras la entrega.

Si tienes dudas sobre el alcance o los requisitos, escríbenos (daniel.sanz@zebraventures.eu) antes de empezar. Preferimos resolver ambigüedades al principio que descubrirlas al final.

Mucha suerte!!