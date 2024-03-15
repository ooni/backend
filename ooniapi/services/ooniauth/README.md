# ooniauth

The OONI Auth service is designed to allow users to authenticate with their
email address to OONI services.

The basic workflow is:

1. Perform a login request by providing your email address
2. Check your email to retrieve the login link
3. Click on the login link to generate a session token that's valid for the
   duration of the session

You may also want to periodically refresh the session token so that it does not
expire.

The tokens which are part of the system are:

- Login tokens, which are sent via email and are tied to an email address
- Session token, which are issued by the API and are tied to a login token
