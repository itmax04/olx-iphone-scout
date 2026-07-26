"""Central DOM selectors for OLX pages. The only place selectors may live.

parser_version must change whenever selectors change materially.
"""

PARSER_VERSION = "olx-dom-v1"

# Search results page
SEARCH_GRID = '[data-testid="listing-grid"]'
SEARCH_CARD = '[data-cy="l-card"]'
SEARCH_EMPTY_MARKER = '[data-testid="empty-state"]'
CARD_LINK = "a"
CARD_TITLE = "h6, h4"
CARD_PRICE = '[data-testid="ad-price"]'
CARD_LOCATION_DATE = '[data-testid="location-date"]'
CARD_IMAGE = "img"
CARD_PROMOTED_MARKER = '[data-testid="adCard-featured"]'

# Detail page
DETAIL_CONTAINER = '[data-testid="offer_title"], [data-cy="ad_title"]'
DETAIL_TITLE = '[data-cy="ad_title"] h4, [data-testid="offer_title"] h4'
DETAIL_PRICE = '[data-testid="ad-price-container"] h3'
DETAIL_DESCRIPTION = '[data-cy="ad_description"] div, [data-testid="ad_description"] div'
DETAIL_PHOTO = '[data-testid="ad-photo"] img'
DETAIL_LOCATION = '[data-testid="map-aside-section"] p, .css-location'
DETAIL_SELLER_NAME = '[data-testid="user-profile-user-name"]'
DETAIL_SELLER_LINK = '[data-cy="seller_card"] a'
DETAIL_SELLER_SINCE = '[data-testid="member-since"]'
DETAIL_SELLER_TYPE_BUSINESS = '[data-testid="business-badge"]'
DETAIL_DELIVERY_BADGE = '[data-testid="courier-btn"], [data-testid="delivery-badge"]'
DETAIL_INACTIVE_MARKER = '[data-testid="ad-inactive-msg"]'

# CAPTCHA / bot-protection markers checked on raw HTML (lowercase).
CAPTCHA_MARKERS = (
    "g-recaptcha",
    "hcaptcha",
    "cf-challenge",
    "captcha-delivery",
    "distil_r_captcha",
    'id="captcha"',
)
