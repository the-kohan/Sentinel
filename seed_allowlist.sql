SET search_path TO sentinel_db;

INSERT INTO known_good (pattern, source, reason, added_by) VALUES
('127.0.0.53:53', 'System DNS', 'Local resolver', 'operator'),
('127.0.0.54:53', 'System DNS', 'Local resolver', 'operator'),
('<WSL2_DNS_IP>:53', 'WSL2 DNS', 'Internal DNS', 'operator'),
('container:<EXAMPLE_SERVICE_1>', 'Docker', 'Example service', 'operator'),
('container:<EXAMPLE_SERVICE_2>', 'Docker', 'Example service', 'operator'),
('container:<EXAMPLE_SERVICE_3>', 'Docker', 'Example service', 'operator'),
('container:<EXAMPLE_SERVICE_4>', 'Docker', 'Example service', 'operator'),
('container:<EXAMPLE_SERVICE_5>', 'Docker', 'Example service', 'operator'),
('container:<EXAMPLE_SERVICE_6>', 'Docker', 'Example service', 'operator'),
('127.0.0.1', 'Loopback', 'Internal traffic', 'operator')
ON CONFLICT (pattern) DO NOTHING;
