-- Servidor descartável sem portas.
CREATE DATABASE aulas_roles_lab;
COMMENT ON DATABASE aulas_roles_lab IS 'aulas-ingles:roles-lab:v1';
REVOKE ALL ON DATABASE aulas_roles_lab FROM PUBLIC;
