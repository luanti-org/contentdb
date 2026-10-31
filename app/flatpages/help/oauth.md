title: OAuth2 API

<p class="alert alert-warning">
    The OAuth2 applications API is currently experimental, and may break without notice.
</p>

ContentDB allows you to create an OAuth2 Application and obtain access tokens
for users.


## Scopes

OAuth2 applications can currently only access public user data, using the whoami API.


## Create an OAuth2 Client

Go to Settings > [OAuth2 Applications](/user/apps/) > Create

The client secret is only shown once, after creating the application. If you lose it,
use "Reset client_secret" on the application's page to get a new one. This
invalidates the old secret.


## Obtaining access tokens

ContentDB supports the Authorization Code OAuth2 method.

### Authorize

Get the user to open the following URL in a web browser:

```
https://content.luanti.org/oauth/authorize/
    ?response_type=code
    &client_id={CLIENT_ID}
    &redirect_uri={REDIRECT_URL}
```

The redirect_url must much the value set in your oauth client. Make sure to URL encode it.
ContentDB also supports `state`.

Afterwards, the user will be redirected to your callback URL.
If the user accepts the authorization, you'll receive an authorization code (`code`).
Otherwise, the redirect_url will not be modified.

For example, with `REDIRECT_URL` set as `https://example.com/callback/`:

* If the user accepts: `https://example.com/callback/?code=abcdef`
* If the user cancels: `https://example.com/callback/`

### Exchange auth code for access token

Next, you'll need to exchange the auth for an access token.

Do this by making a POST request to the `/oauth/token/` API:

```bash
curl -X POST https://content.luanti.org/oauth/token/ \
    -F grant_type=authorization_code \
    -F client_id="CLIENT_ID" \
    -F client_secret="CLIENT_SECRET" \
    -F code="abcdef" 
```

<p class="alert alert-warning">
    <i class="fas fa-exclamation-circle me-2"></i>
    You should make this request on a server to prevent the user
    from getting access to your client secret.
</p>

If successful, you'll receive:

```json
{
    "success": true,
    "access_token": "access_token",
    "token_type": "Bearer"
}
```

Each auth code can only be redeemed once, and the access token is only returned
at this point. If the user authorizes your application again, their previous
access token keeps working until you redeem the new code, which replaces it.

If there's an error, you'll receive a standard API error message:

```json
{
    "success": false,
    "error": "The error message"
}
```

Possible errors:

* Unsupported grant_type, only authorization_code is supported
* Missing client_id
* Missing client_secret
* Missing code
* client_id and/or client_secret is incorrect
* Incorrect code. It may have already been redeemed

### Check access token

Next, you should check the access token works by getting the user information:

```bash
curl https://content.luanti.org/api/whoami/ \
    -H "Authorization: Bearer YOURTOKEN"
```
