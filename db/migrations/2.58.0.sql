-- Auditoría UX v2.58.0: el portal cliente no tenía forma de recuperar la
-- contraseña ni el panel admin — un usuario bloqueado necesitaba que alguien
-- con acceso a la DB le reseteara la contraseña a mano. Guarda el HASH del
-- token (SHA-256), nunca el token crudo, mismo criterio que api_keys.key_hash.
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id     INT UNSIGNED  NOT NULL,
    token_hash  CHAR(64)      NOT NULL UNIQUE,
    expires_at  DATETIME      NOT NULL,
    used_at     DATETIME      NULL,
    created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
