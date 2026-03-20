from urllib.parse import urlparse
import ipaddress
import socket
import requests
from requests.exceptions import RequestException
import lxml.html

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import UserRateThrottle

class ProxyScrapeView(APIView):
    """
    Secure proxy to fetch raw HTML from a given URL for frontend XPath parsing.
    Prevents SSRF and protects against oversized/hanging responses.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    MAX_SIZE_BYTES = 1024 * 1024  # 1 MB limit
    TIMEOUT_SECONDS = 5
    ALLOWED_SCHEMES = {'http', 'https'}

    def get(self, request, *args, **kwargs):
        url = request.query_params.get('url')
        xpath = request.query_params.get('xpath')
        if not url:
            return Response({'error': 'URL parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # 1. URL Validation
        try:
            parsed_url = urlparse(url)
            if parsed_url.scheme not in self.ALLOWED_SCHEMES:
                return Response({'error': 'Only HTTP and HTTPS are allowed.'}, status=status.HTTP_400_BAD_REQUEST)
            
            # DNS resolution to block internal IPs (SSRF protection)
            hostname = parsed_url.hostname
            if not hostname:
                return Response({'error': 'Invalid URL hostname.'}, status=status.HTTP_400_BAD_REQUEST)

            ip = socket.gethostbyname(hostname)
            ip_obj = ipaddress.ip_address(ip)
            if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_multicast:
                return Response({'error': 'Requests to private IPs are forbidden.'}, status=status.HTTP_403_FORBIDDEN)

        except (ValueError, socket.gaierror):
            return Response({'error': 'Invalid URL or unresolvable hostname.'}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Secure Fetching
        try:
            # Prevent DNS Rebinding: Connect to the validated IP, set original hostname in Host header
            safe_url = url.replace(hostname, ip, 1)
            headers = {
                # Some sites block requests that look like generic Python scrapers
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Host': hostname
            }
            
            # Disable redirects to prevent following to an internal IP (SSRF bypass via 3xx)
            with requests.get(safe_url, headers=headers, stream=True, timeout=self.TIMEOUT_SECONDS, allow_redirects=False) as r:
                if r.status_code in (301, 302, 303, 307, 308):
                    return Response({'error': 'Redirects are not allowed.'}, status=status.HTTP_400_BAD_REQUEST)
                r.raise_for_status()
                
                # Check declared content type strictly
                content_type = r.headers.get('Content-Type', '')
                allowed_types = ['text/html', 'text/xml', 'application/xhtml+xml', 'text/plain']
                if not any(t in content_type for t in allowed_types):
                     return Response({'error': 'Unsupported content type. Only HTML/XML/Text is permitted.'}, status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)

                # Read in chunks to enforce size limit securely
                content = b''
                for chunk in r.iter_content(chunk_size=8192):
                    content += chunk
                    if len(content) > self.MAX_SIZE_BYTES:
                        return Response({'error': 'Response payload too large.'}, status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)

                html_text = content.decode('utf-8', errors='replace')
                
                if xpath:
                    try:
                        # Safe XML parser with external entities disabled (XXE prevention)
                        parser = lxml.html.HTMLParser(resolve_entities=False)
                        tree = lxml.html.fromstring(html_text, parser=parser)
                        
                        # run xpath
                        elements = tree.xpath(xpath)
                        
                        if not elements:
                             return Response({'result': None})
                             
                        # xpath might return an element or a direct string (e.g if they used /text())
                        first_match = elements[0]
                        if isinstance(first_match, str):
                            result_text = first_match.strip()
                        else:
                            # If they matched an element, get its text content
                            result_text = getattr(first_match, 'text_content', lambda: str(first_match))().strip()
                            
                        return Response({'result': result_text})
                    except Exception as e:
                        return Response({'error': f'Failed to evaluate XPath: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

                return Response({'html': html_text})

        except requests.exceptions.Timeout:
            return Response({'error': 'Request timed out.'}, status=status.HTTP_504_GATEWAY_TIMEOUT)
        except requests.exceptions.RequestException as e:
            return Response({'error': f'Failed to fetch URL: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)
