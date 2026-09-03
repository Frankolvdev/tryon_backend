class DisposableEmailService:
    BLOCKED_DOMAINS = {
        "10minutemail.com",
        "10minutemail.net",
        "20minutemail.com",
        "discard.email",
        "discardmail.com",
        "dispostable.com",
        "emailondeck.com",
        "fakeinbox.com",
        "generator.email",
        "getnada.com",
        "guerrillamail.com",
        "guerrillamail.net",
        "guerrillamail.org",
        "maildrop.cc",
        "mailinator.com",
        "mailnesia.com",
        "mintemail.com",
        "moakt.com",
        "mytemp.email",
        "sharklasers.com",
        "spam4.me",
        "temp-mail.org",
        "tempail.com",
        "tempemail.com",
        "tempmail.com",
        "tempmail.net",
        "tempmailo.com",
        "throwawaymail.com",
        "trashmail.com",
        "yopmail.com",
        "yopmail.fr",
        "yopmail.net",
    }

    def domain(
        self,
        email: str,
    ) -> str:
        value = email.strip().lower()

        if "@" not in value:
            return ""

        return value.rsplit(
            "@",
            1,
        )[1]

    def is_disposable(
        self,
        email: str,
    ) -> bool:
        domain = self.domain(email)

        if not domain:
            return True

        if domain in self.BLOCKED_DOMAINS:
            return True

        return any(
            domain.endswith(
                "." + blocked
            )
            for blocked
            in self.BLOCKED_DOMAINS
        )


disposable_email_service = (
    DisposableEmailService()
)