"""Custom InvenioRDM supplements to Werzeug's map.py.

This code is in support of providing `invenio_url_for`, the RDM supplement
to Flask's `url_for` which allows any part of the application (in the broad
sense of the term) to generate URLs even if those URLs are for views registered
in another Flask application. Other developer niceties are included.

Werkzeug map:
https://github.com/pallets/werkzeug/blame/main/src/werkzeug/routing/map.py
"""

from abc import ABC, abstractmethod

from flask import Flask, current_app
from werkzeug.routing import BuildError, Map, Rule

from invenio_base.app import blueprint_loader


class InvenioUrlsBuilder(ABC):
    """Interface of class in charge of producing urls."""

    @abstractmethod
    def build(self, endpoint, values, method=None):
        """Build current or other app url."""


class InvenioAppsUrlsBuilder(InvenioUrlsBuilder):
    """Builds URLs with some knowledge of Invenio (app-rdm)."""

    def __init__(
        self,
        cfg_of_app_prefix,
        cfg_of_other_app_prefix,
        groups_of_other_app_entrypoints,
    ):
        """Constructor."""
        self.cfg_of_app_prefix = cfg_of_app_prefix
        self.cfg_of_other_app_prefix = cfg_of_other_app_prefix
        self.groups_of_other_app_entrypoints = groups_of_other_app_entrypoints

    def setup(self, app, **kwargs):
        """Sets up the object for url generation.

        It does so by building an internal url_map that it will reuse.

        This is called before the application is fully setup (not in an application
        context).
        """
        # Create a tmp Flask app
        app_tmp = Flask("InvenioAppsUrlsBuilder")
        app_tmp.config["BLUEPRINTS_URL_PREFIXES"] = app.config.get(
            "BLUEPRINTS_URL_PREFIXES", {}
        )

        blueprint_loader(
            app_tmp,
            entry_points=self.groups_of_other_app_entrypoints,
        )

        # Copy the Rules minus the view_functions (don't need them)
        self.url_map = Map(
            [Rule(r.rule, endpoint=r.endpoint) for r in app_tmp.url_map.iter_rules()]
        )

    def prefix(self, site_cfg):
        """Return site prefix."""
        return current_app.config[site_cfg]

    def build(self, endpoint, values, method=None):
        """Build full url of any registered endpoint with appropriate prefix.

        This is called within an application context.
        """
        # 1- Try to build url from current app
        try:
            # TODO: Consider if cache on application context (g)
            url_adapter = current_app.url_map.bind("")
            url_relative = url_adapter.build(
                endpoint, values, method=method, force_external=False
            )
            return self.prefix(self.cfg_of_app_prefix) + url_relative
        except BuildError:
            # The endpoint may be from the complementary blueprints
            pass

        # 2- Try to build url from complementary url_map
        # TODO: Consider if cache on application context (g)
        url_adapter = self.url_map.bind("")
        url_relative = url_adapter.build(  # type: ignore[union-attr]
            endpoint,
            values,
            method=method,
            force_external=False,  # necessary?
        )
        return self.prefix(self.cfg_of_other_app_prefix) + url_relative


def create_invenio_apps_urls_builder_factory(
    cfg_of_app_prefix, cfg_of_other_app_prefix, groups_of_other_app_entrypoints
):
    """Create the factory for invenio_urls_builder that knows about dual app setup.

    This function is made with knowledge of invenio-app mechanisms as a
    convenience, but it produces a factory that produces an implementation of
    InvenioUrlsBuilder. This means invenio-app
    can swap it out easily for a different URL generator - just need to
    produce a builder that implements InvenioUrlsBuilder's interface.

    :param cfg_of_site_prefix: str. config for current app prefix
    :param cfg_of_other_site_prefix: str. config for other app prefix
    :param groups_of_other_site_entrypoints: entrypoints groups to load
                                             blueprints of other app
    """

    def _factory(app, **kwargs):
        builder = InvenioAppsUrlsBuilder(
            cfg_of_app_prefix,
            cfg_of_other_app_prefix,
            groups_of_other_app_entrypoints,
        )
        builder.setup(app, **kwargs)
        return builder

    return _factory


def invenio_url_for(
    endpoint,
    *,
    # _anchor = None,  # TODO
    _method = None,
    **values,
):
    """A URL generator for the Invenio reality.

    This function can build full (external) URLs for the current app and for setup
    endpoints. For maximum flexibility it leaves most of the work to `invenio_urls`
    and instance of `InvenioUrlsBuilder` setup and assigned at Flask app creation.
    This solves the problem of generating URLs for a Flask app when inside
    another Flask app.

    Because of this and to simplify things, `invenio_url_for` only generates
    external URLs (with scheme and server name configured by the instance of
    `InvenioUrlsBuilder`). This makes its interface slightly different
    than `url_for`'s.
    """

    return current_app.invenio_urls.build(
        endpoint,
        values,
        method=_method,
        # _anchor=_anchor,  # TODO
    )
