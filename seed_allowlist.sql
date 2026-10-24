INSERT INTO known_good (pattern, source, reason, added_by) VALUES
('127.0.0.53:53', 'WSL2 DNS', 'System resolver', 'operator'),
('127.0.0.54:53', 'WSL2 DNS', 'System resolver', 'operator'),
('10.255.255.254:53', 'WSL2 DNS', 'Internal DNS', 'operator'),
('container:n8n', 'Docker', 'Workflow automation', 'operator'),
('container:ollama', 'Docker', 'Local LLM', 'operator'),
('container:postgres', 'Docker', 'Primary DB', 'operator'),
('container:redis', 'Docker', 'Cache', 'operator'),
('container:qdrant', 'Docker', 'Vector DB', 'operator'),
('container:searxng', 'Docker', 'Search', 'operator'),
('127.0.0.1', 'Loopback', 'Internal traffic', 'operator')
ON CONFLICT (pattern) DO NOTHING;
